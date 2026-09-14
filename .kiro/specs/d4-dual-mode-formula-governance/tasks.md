# Tasks — D4双模式公式治理与36底稿覆盖

- [x] 1. C0模板/identity：建立D4-1..36 owner矩阵，逐项读取finder索引及权威源模板；D4-4/8/12按已有能力只收口缺口，不重复已有owner。
  - _Requirements: 1.1, 1.2, 1.3, 8.1_
- [x] 2. C1sync：冻结共享协议、字段级自动合并、同字段冲突轨迹、durable ack/applied及canonical refresh。
  - _Requirements: 2.1, 2.2, 2.3_
- [x] 3. C2formula：冻结wp_id公式key、preset/custom、F-SHELL、schema白名单、CAS和缺失/损坏/stale/blocked。
  - _Requirements: 3.1, 3.2, 3.3, 3.4_
- [x] 4. C3linkage：冻结真实DAG、单writer、联动接收端及TB/A13显式发布边界。
  - _Requirements: 4.1, 4.2, 5.1_
- [x] 5. C0-C3 platform contracts：冻结导入identity、四表复用、权限/CAS、幂等迁移；只覆盖相关产物。
  - _Requirements: 5.2, 6.1, 7.1_
- [x] 6. C4逐表验收：登记36行source/contract/roundtrip/formula-conflict/permission/Playwright状态，UNVERIFIABLE不得假绿。
  - _Requirements: 8.1_
- [x] 7. C4行为守卫和变异：验证矩阵、三方合并、公式边界、真实DAG和发布确认。
  - _Requirements: 2.2, 3.2, 4.2, 5.1_

## Task Dependency Graph
```json
{"waves":[{"wave":1,"tasks":["1"],"rationale":"C0先核定矩阵与模板"},{"wave":2,"tasks":["2","3"],"rationale":"C1/C2可并行冻结"},{"wave":3,"tasks":["4","5"],"rationale":"C3与平台契约依赖C1/C2"},{"wave":4,"tasks":["6"],"rationale":"C4逐表验收依赖前序契约"},{"wave":5,"tasks":["7"],"rationale":"行为守卫最后执行"}],"blocking":{"1":"owner/template未核定不得冻结矩阵","2":"sync未冻结不得声明applied","3":"formula未冻结不得接入公式"}}
```

## P0 修复实施任务（2026-09-14，append-only；上方 1-7 已完成条目文字不动）

- [x] P0-5. D4 导入编辑权限门 + 导出只读收口（Req 7）
  - d4_import_data 首句 authorize_wp_edit + check_consol_lock；export-template/export-data 接 authorize_wp_read（deps.py 新增）；_parse_wp_uuid 兜非法 UUID→404。
  - 证据：tests/test_d4_import_permission_gate.py 10 passed。发现端点已有 router-level dedicated_wp_gate（契约修正）。
  - _Requirements: 7_
- [x] P0-4. checklist_responses 乐观锁 CAS（Req 7）
  - V161/R161 加 content_version（真实 PG 已应用 schema_version=161）；_upsert_checklist_response（FOR UPDATE + If-Match，409 不覆盖）；三处写路径改用；d4_import_data 加 base_version 参 + 回带 content_version。
  - 证据：tests/test_d4_import_cas.py 4 passed。
  - _Requirements: 7_
- [x] P0-3. TB 显式发布确认 + 权限 + 幂等 + 前端按钮（Req 5.1）
  - handler publish_confirmed 门 + _publisher_can_publish（fail-closed）；V162/R162 tb_publish_ack 幂等（真实 PG schema_version=162）；专用发布端点；GtAuditSheet.vue "发布到试算表"按钮 + 二次确认。
  - 证据：test_cycle_linkage_handlers_integration.py 22 passed（含普通保存不写TB/无权拒/幂等不双写）；test_publish_determination_to_tb.py 6 passed；GtAuditSheet.publishTb.spec.ts 4 passed。
  - 🔴 **结论修正（见 P0-3d，2026-09-14）**：本条前端只把发布按钮 + 二次确认接在**通用 GtAuditSheet**，但 AC-3.4 点名的 **D4-1 实际用专属组件 d4-operating-revenue 渲染，绕过了该门**（经 `PUT /trial-balance/writeback` 直写 TB）。即本条声称的「前端按钮」对 D4-1 及所有专属组件不生效，AC-3.4 直至 P0-3d 才对 D4-1 真正满足；其余 D~N 专属组件仍未接入（P0-3d 已登记为遗留缺口）。
  - _Requirements: 5.1_
- [x] P0-3c. 发布到试算表 API 级端到端实测（隔离测试项目，真实 PG）
  - 造隔离测试项目 seed 脚本 `backend/scripts/e2e/seed_d4_publish_e2e.py`（幂等 upsert + --dry-run + --purge）：project=E2E-D4发布测试项目_请勿动_2099（固定 UUID d4e2e000-…-d401，audit_year=2099，绝不撞真实项目/真实金额）、admin edit 成员、TB 6001/6051（收入类，audited 初值 0）、wp_index D4-1 + working_paper（wp_id d4e2e000-…-d403）。已 --dry-run + 真跑并 PG 校验。
  - API E2E `backend/tests/test_d4_publish_e2e_live.py`（打真实运行后端 + 真实 PG，无 seed/后端则整文件 skip）：**4 passed** —— ①happy：POST publish-to-tb → published=True，TB 6001 审定数=1000000+5000+0=1005000、6051=200000+0-3000=197000，tb_publish_ack 恰 1 条 accounts_updated=2；②幂等：同 publish_token 再发一次不二次回写（哨兵值验证）、ack 仍 1 条；③无 audit_rows → 400 且 TB 不变；④非审定表 sheet → 400 且 TB 不变。
  - 🔴 实测中发现并修复真实根因 bug（此前 P0-3b 无法验证的深层原因）：`event_handlers_cycle_linkage.py` 回写 handler `from app.models.trial_balance_models import TrialBalance` 引用**不存在的模块**（全仓其余 30+ 处均从 `app.models.audit_platform_models` 导入），被 handler 外层 `try/except Exception: logger.warning` 静默吞掉 → **TB 回写从未真正生效**。已修为正确模块路径；grep 确认全仓仅此一处错误路径。回归：test_publish_determination_to_tb.py(6)+test_cycle_linkage_handlers_integration.py(22)=28 passed 无回归。
  - 修改文件：`backend/app/services/event_handlers_cycle_linkage.py`（import 修复）、新增 `backend/scripts/e2e/seed_d4_publish_e2e.py` + `backend/tests/test_d4_publish_e2e_live.py`。
  - _Requirements: 5.1, 8_
- [x] P0-3b. 发布到试算表 Playwright UI 全链路端到端实测（隔离测试项目，真实 9980+PG）
  - 前置：seed_d4_publish_e2e.py **增强**——除 project/TB/wp 外，新增 `TEST_CHECKLIST_RESPONSES` 写 D4-1 审定表渲染数据（`D4-1-rows` 主营 6001 + 其他 6051 两手工行 + per-field currentUnadjusted 1000000/200000、Aje/Rje=0 + `D4-1-adj-tb-6001/6051` TB 对账影子值），否则审定表渲染全空（原 seed 只建空壳 working_paper，审定行来自 checklist_responses）。新增 `--check`（查 TB 6001/6051 audited + tb_publish_ack 计数）/`--reset-tb`（audited 归零 + 清 ack）；`--purge` 加清 checklist_responses。rowId 用无短横 `seedmain`/`seedother`（避 `extractRowIdFromItemId` 的 lastIndexOf('-')）。
  - Playwright 全链路（localhost:3030 + 真实 9980 + 真实 PG，隔离项目 d4e2e000-…-d401 / year 2099）：①admin 登录 → `/projects/{pid}/workpapers/{wpId}/edit` → 「营业收入审定表D4-1」tab；②审定表**渲染有数**：主营(E2E)未审 1,000,000/审定 1,000,000.00、其他(E2E)未审 200,000/审定 200,000.00、合计审定 1,200,000.00、TB 对账行「试算平衡表数（6001+6051）：1,200,000.00 核对一致」（此前全「-」的假象已消除）；③点「确认审定（回写TB）」→ 弹**二次确认**对话框「发布到试算表确认」（中文，确认发布/取消）；④点确认发布 → `POST /api/workpapers/{wpId}/audit-determination/publish-to-tb` **200 OK**（body sheet_name=审定表D4-1、audit_rows 6001=1000000/6051=200000），网络面板确认**无** `PUT /trial-balance/writeback` 绕过调用、0 console error；⑤SQL 取证 TB **6001 0.00→1,000,000.00、6051 0.00→200,000.00**、tb_publish_ack 生成；⑥**幂等**：SQL 置哨兵 99999 → 重复点击+确认发布（同内容 → 同 content-derived token）→ TB **保持 99999 未被覆写回**、ack 未新增（`tb_publish_ack ON CONFLICT DO NOTHING` 去重生效）。
  - 收尾：TB 归零 + ack 清空 + 临时脚本删除 + 关浏览器；全程仅触碰隔离项目，真实审计项目零触碰。
  - 🔴 实测中定位并修复真实缺口（情形B，见 P0-3d）：D4-1 用 `d4-operating-revenue` 组件渲染（**非 GtAuditSheet**），此前「确认审定（回写TB）」经 `PUT /projects/{pid}/trial-balance/writeback` 直写 audited_amount，**绕过** P0-项3 的 `publish_confirmed` 显式确认门 —— 门只接在 GtAuditSheet。故 P0-3b 此前的「UI 可达性已测但全链路卡后端 stale」结论**不成立**（真实卡点不是后端 stale，而是 D4-1 根本没接门）。
  - 修改文件：`backend/scripts/e2e/seed_d4_publish_e2e.py`（seed 增强 + --check/--reset-tb）。
  - _Requirements: 5.1, 8_
- [x] P0-3d. 修正 P0-项3 显式发布门未接到 D4-1 实际渲染组件（情形B 缺口，AC-3.4）
  - 🔴 缺口（如实修正 P0-3/3c 结论偏差）：requirements.md **AC-3.4 明写「前端 D4-1/审定表有显式发布 + 二次确认」**，但 P0-3 只把发布按钮 + 二次确认接在**通用** `GtAuditSheet.vue`。D4-1 实际用**专属组件** `d4-operating-revenue`（`GtD4OperatingRevenue.vue` → `D4TabAdjudication.vue`）渲染，其「确认审定（回写TB）」= `useD4Adjudication.publishAdjudicated` 只 dispatch CustomEvent `d4:writeback-trial-balance` → `GtD4OperatingRevenue.handleD4Writeback` → `useD4FormData.writebackTrialBalance` → `PUT /projects/{pid}/trial-balance/writeback`（`trial_balance.py::writeback_audited_amount`）**直写** `trial_balance.audited_amount`，仅 `require_project_access("edit")`，**无 publish_confirmed 门 / 无二次确认 / 无 tb_publish_ack 幂等**。⇒ P0-项3 的显式发布门在 D4-1（及所有专属组件）上**形同虚设**，AC-3.4 未真正满足。
  - 修复（前端，对齐 GtAuditSheet 范式，最小改动）：`useD4Adjudication.publishAdjudicated` 改为 async 门控 —— `ElMessageBox.confirm` 二次确认（中文「发布到试算表确认」）→ `POST /api/workpapers/{wpId}/audit-determination/publish-to-tb`（sheet_name=审定表D4-1，audit_rows 主营小计→6001 / 其他小计→6051，携 current_unadjusted/adj_amount/reclass_amount）→ 后端算审定数、校发布权限、发 `publish_confirmed=True` + token → 回写 handler 幂等回写 TB。**移除**绕过门的 `d4:writeback-trial-balance` dispatch（普通保存对 TB 已是 no-op）；保留 `substantive:adjudicated`（供附注/检查表下游刷新）。`D4TabAdjudication.vue` 按钮加 `:loading="publishing"`。
  - 证据：新增 `d4AdjudicationPublishGate.spec.ts` **4 passed**（确认后调 publish-to-tb 端点 body 含 sheet_name(D4-1)+audit_rows 6001/6051；取消二次确认不发请求；readonly 不发请求；**不再** dispatch 绕过门的 d4:writeback-trial-balance）；旧 `d4AdjudicationRowLinkage.spec.ts` **5 passed** 无回归；后端未改，回归 `test_publish_determination_to_tb.py`(6)+`test_cycle_linkage_handlers_integration.py`(22)=**28 passed**、live `test_d4_publish_e2e_live.py` **4 passed**（真实 9980+PG）。Playwright 全链路见 P0-3b。
  - 🔴 **遗留同类缺口（本任务未修，如实登记）**：几乎所有 D~N 专属组件（D2-D7/E1/F1-F5/G 系列/K1-K5/L1-L8/M/N/H6/I6）的审定回写均经 `useXFormData.writebackTB`/`writebackTrialBalance` → 同一 `PUT /trial-balance/writeback` 绕过门端点（grep `trial-balance/writeback` 前端 20+ 命中）。本任务只按 scope 修 D4-1；其余专属组件的显式发布门接入建议另立专项（可选：给 `PUT /trial-balance/writeback` 端点本身加 publish_confirmed 门 + 幂等，或逐组件改走 publish-to-tb）。**这是 P0-项3 收口范围的真实边界，勿视作 D4-1 已修即全线闭合。**
  - 修改文件：`audit-platform/frontend/src/components/workpaper/composables/useD4Adjudication.ts`、`audit-platform/frontend/src/components/workpaper/d4/core/D4TabAdjudication.vue`、新增 `audit-platform/frontend/src/components/workpaper/composables/__tests__/d4AdjudicationPublishGate.spec.ts`。
  - _Requirements: 5.1_
- [x] P0-1. wp_formula 稳定键三层一致（Req 3.1）
  - V163/R163 加 stable_sheet_key/row_key/field_key + needs_review + 部分唯一索引（真实 PG schema_version=163，存量回填正确）；stable_key.py 单一真源；ORM + service 双写；旧键保留一版。
  - 证据：tests/test_wp_formula_stable_key.py 17 passed（含 2 PBT）；test_wp_formula_layer_contract.py 5 passed。
  - _Requirements: 3.1_
- [x] P0-2. 公式四态 + 导入保护（Req 3.2/3.3）
  - formula_state.py 单一真源（ok/missing/damaged/blocked）；FormulaResult.blocked/.state + FormulaBlockedError；未注册函数不再静默返 0；save 对 damaged/blocked 拒绝写库保留原始表达式。
  - 证据：tests/test_formula_state_classification.py 22 passed（含 4 PBT）；test_wp_formula_import_protection.py 4 passed；formula_engine 6 文件回归 201 passed。
  - _Requirements: 3.2, 3.3_
- [x] P0-fix. 过时 fixture 修复 + 连带暴露的真实生产 bug（2026-09-14 收尾）
  - 背景：P0-1/P0-2（Req10 ownership 守卫 c267ce8c + 公式四态保护）使 6 个 wp_formula 测试文件的旧 fixture 过时——`_make_session` 只建 wp_formula 表不建 working_paper，`save()`/`list_by_wp()` 的 `_verify_wp_ownership` 查 working_paper → sqlite `no such table`；且 PBT 生成器造 `<`/中文占位表达式被四态保护判 damaged/blocked。
  - 修复 6 文件（对齐 test_wp_formula_import_protection.py 的 patch.object(WpFormulaService,"_verify_wp_ownership",AsyncMock(True)) 隔离模式，ownership 另有 test_ownership_guard_pbt 专测覆盖）：test_wp_formula_three_type.py（+autouse stub，last_computed_at 断言按 P5「save 不写、执行后 coordinator 记」更新）/ test_wp_formula_roundtrip_pbt.py / test_wp_formula_endpoint.py / formula_management/{test_pbt_p06_save_roundtrip, test_pbt_p07_dangling_reject, test_pbt_p28_source_roundtrip, test_reference_resolver}.py（补 stub + list_by_wp 传 project_id + 生成器约束为合法 DSL）。
  - **连带修真实生产 bug**：`wp_formula_service.py` reference 悬空分支 `ref_res.issue.description`（属性访问）——但 `ReferenceResolution.issue` 类型为 `dict`，真实运行 save(reference,悬空) 必 AttributeError→500；改 `ref_res.issue.get("description", …)`。触类旁通 grep 全 app 无同类 `.issue.<attr>` 残留。
  - 证据：上述 9 文件合计 25 passed（含 P12/P6/P7/P28 PBT）；test_ownership_guard_pbt.py 5 passed（生产改动零回归）。
  - _Requirements: 3.1, 3.2, 3.3, 10_
