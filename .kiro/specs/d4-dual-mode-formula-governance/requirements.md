# D4 双模式公式治理与36底稿覆盖总纲

## Introduction
本总纲是D4-1..D4-36的共同契约与编排入口。它只约束HTML/Excel双模式、公式、联动、身份、权限、版本和验收集成，不实现平台引擎，不要求平台77项任务全绿。运行时模板必须由`wp_template_finder`及索引选择，权威模板仅为`backend/wp_templates/`，不得使用参考副本虚构内容。

## Requirements
### Requirement 1 — 范围与逐表owner矩阵
1. SHALL 为D4-1..D4-36逐`wp_code`登记owner、目标、状态（已覆盖/待核定/N/A）；N/A必须保留分母，不得抹除。
2. 已有owner不得重复立项：D4-2由`d4-revenue-matrix-bidirectional`、D4-9由`d4-9-customer-structure-bidirectional-writeback`、D4-10/11由`d4-price-analysis-writeback-linkage`负责；D4-5等已覆盖项不得新建gap。
3. D4-4、D4-8、D4-12若无明确owner，必须进入gap closure；仅以源模板和运行时finder核定后冻结。

### Requirement 2 — 共享同步与冲突
1. HTML与Excel均经`ContentMutationService`及`useWorkpaperSyncBridge`。
2. 不同字段自动合并；同字段冲突保留base/current/incoming、决策和轨迹，禁止Excel优先或最后写胜出。
3. durable ack仅表示决策已持久化，不等于applied；canonical rematerialize及目标content version确认后才算applied。

### Requirement 3 — 公式定义与custom
1. 有效定义 key 固定为`wp_id + stable_sheet_key + row_key + field_key + custom`；`preset_version`是定义版本，不是业务target identity的一部分；普通值override属于另域。
2. F-SHELL v2仅允许白名单命令表达式/引用/参数；禁止remark或field_overrides充当公式库，编辑schema禁止eval和外链。缺失公式与损坏公式分态，输入版本stale不得静默接受。
3. OO模板公式是同一公式定义的投影；mask保护公式值。Excel用户改公式必须解析、校验、CAS审计；不能保留原字节时显式blocked，不得静默仅存值。
4. 预设升级保留custom；删除custom后恢复preset；依赖版本变化产生stale。

### Requirement 4 — 表内/表间DAG
1. 表内、表间均可编辑；同scope只有一个公式writer。
2. 执行依赖必须是实际DAG，不能按表号禁止合理引用；循环和stale必须显式失败或标记。

### Requirement 5 — 联动边界与发布
1. 风险发现不等于错报；TB/A13发布必须显式确认且幂等、durable ack；模式切换不得发布。
2. 四表取数必须复用`app/services/four_table/`及`ReportLineAccountSpec`，不得复制科目SQL。

### Requirement 6 — 导入结构身份
导入导出必须保留sheet/table/区域/稳定row key/公式mask身份；结构变更走`ContentMutationService` mutation plan，拒绝位置猜测和静默扁平化。

### Requirement 7 — 权限、版本、迁移
按角色、scope、版本校验读写；拒绝过期CAS并记录审计。迁移必须幂等、可回滚，且不得把平台全局未完成作为D4全局阻塞。

### Requirement 8 — 逐表验收与milestone
每个wp_code必须有模板证据、contract/identity、HTML→Excel→HTML roundtrip、公式/冲突、权限及Playwright验收状态。按可验证milestone解锁子组；不可验证记UNVERIFIABLE，不得假绿。

## Acceptance Coverage
每条Requirement均由总纲设计R1-R8和tasks验收映射；逐表矩阵不得省略待核定项。


## P0 修复验收补充（2026-09-14 实施，append-only）

> 本节把总纲 Req 3/5/7 中已声明的契约落到**可验证的验收标准 + 现状证据**。对应 5 项 P0 修复。
> 每项标注实现文件与测试证据；真实外部服务(PG)已用、前端服务未起处如实记录。

### P0-1 公式稳定键三层一致（对应 Req 3.1）
- **AC-1.1** wp_formula identity = `(wp_id, stable_sheet_key, row_key, field_key)`；`preset_version` 不进 identity。
- **AC-1.2** sheet 展示名重命名（加/去排序前缀、空白差异）不改稳定键。
- **AC-1.3** `target_cell` 无法解析为 A1（命名单元）→ 显式标 `stable_key_needs_review`，不静默丢。
- **AC-1.4** 迁移幂等可回滚（V163/R163），旧键 `uq_wp_formula_wp_sheet_cell` 保留一版过渡；存量行安全回填。
- **证据**：迁移已在真实 PG 应用（schema_version=163，2 存量行回填正确，0 needs_review）；
  单一真源 `app/services/formula_management/stable_key.py`；ORM 4 列 + 部分唯一索引；service 双写；
  `tests/test_wp_formula_stable_key.py` 17 passed（含 P1/P2 PBT）；`tests/test_wp_formula_layer_contract.py` 5 passed。

### P0-2 公式四态 missing/damaged/blocked + 导入保护（对应 Req 3.2/3.3）
- **AC-2.1** 四态互斥：`missing`(key 不存在)/`damaged`(AST 解析失败)/`blocked`(非白名单函数/eval/exec/URL/外链)/`ok`。
- **AC-2.2** 引擎不再对未注册函数静默返 0 冒充正常：`blocked` 时 `ok=False`、`state='blocked'`（value 仍给，语义明确）。
- **AC-2.3** 保存/导入入口对 damaged/blocked 拒绝写库，返回 issue 保留**原始表达式**作证据，不静默仅存值。
- **证据**：`app/services/formula_management/formula_state.py`（单一真源）；`formula_engine` 加
  `FormulaBlockedError`+`FormulaResult.blocked/.state`+`_is_blocked_formula`；`WpFormulaService.save` 态保护；
  `tests/test_formula_state_classification.py` 22 passed（含 4 PBT）；`tests/test_wp_formula_import_protection.py` 4 passed；
  改造 `test_formula_engine_registry` 旧"未注册返0"契约为 blocked；formula_engine 6 文件回归 201 passed。

### P0-3 TB/A13 显式发布确认 + 幂等（对应 Req 5.1）
- **AC-3.1** 普通保存/模式切换**不回写** trial_balance；仅 `extra.publish_confirmed is True` 才回写。
- **AC-3.2** 发布者权限服务端可验证（`confirmed_by` 须存在启用用户且具 WORKPAPER_WRITE，fail-closed）。
- **AC-3.3** 幂等：同一确认（`publish_token` 唯一）重复投递只生效一次（`tb_publish_ack` ON CONFLICT DO NOTHING）。
- **AC-3.4** 前端 D4-1/审定表有显式"发布到试算表"操作 + 二次确认（中文）。
- **证据**：`event_handlers_cycle_linkage._on_d_audit_determination_saved` 加确认门 + `_publisher_can_publish`；
  V162/R162 建 `tb_publish_ack`（真实 PG schema_version=162）；专用端点
  `POST /api/workpapers/{wp_id}/audit-determination/publish-to-tb`；前端 `GtAuditSheet.vue` "发布到试算表"按钮；
  `tests/test_cycle_linkage_handlers_integration.py` 22 passed（含普通保存不写TB/无权拒/幂等不双写）；
  `tests/test_publish_determination_to_tb.py` 6 passed；`GtAuditSheet.publishTb.spec.ts` 4 passed。
  **Playwright 端到端未实测**（前端 3030 未运行；且不向真实审计项目发布测试金额）。

### P0-4 D4 导入并发一致性/CAS（对应 Req 7）
- **AC-4.1** checklist_responses 加乐观锁版本 `content_version`；导入可选带 `base_version` 做 If-Match。
- **AC-4.2** `base_version` 与服务端当前版本不符 → 409 `VERSION_CONFLICT`，不静默覆盖；相符 → +1；无 `base_version` → 创建/覆盖（兼容旧客户端）。
- **AC-4.3** `SELECT ... FOR UPDATE` 串行化"读版本→比对→写"，消除 READ COMMITTED 竞态窗口。
- **证据**：V161/R161 加列（真实 PG schema_version=161，列已确认）；`_upsert_checklist_response` 乐观锁助手；
  三处写路径(D4-31/主体/D4-13)全改用；`d4_import_data` 加 `base_version` 查询参、响应回带 `content_version`；
  `tests/test_d4_import_cas.py` 4 passed。

### P0-5 D4 导入编辑权限门禁（对应 Req 7）
- **AC-5.1** 导入(写)首句显式 `authorize_wp_edit`（readonly/qc/非成员→403，底稿不存在→404）+ `check_consol_lock`(锁定→423)，先于任何解析与 DB 写。
- **AC-5.2** 导出(读)按 readonly 项目权限收口（`authorize_wp_read`），不误伤只读成员，拒绝非成员。
- **AC-5.3** 无权者不产生任何 DB 变更（readonly/qc 在查库前即拒）。
- **现状证据修正**：实测发现 `/api/workpapers/{wp_id}/d4/*` 路由在 router_registry 注册时**已附加** router-level
  `dedicated_wp_gate`（Wp_Bound_Gate 可见性/委派门，按 HTTP method 分 read/write）——此前契约报告只看函数签名
  Depends(get_current_user+get_db) 漏看了 router-level 依赖，故端点**并非"零权限"**。本次新增的项目级编辑权 + 合并锁
  是**额外纵深防御**，且补上了可见性门**不覆盖的合并锁**。
- **证据**：`deps.py` 新增 `authorize_wp_read`；`_d4_import_export.py` 三端点接入门禁 + `_parse_wp_uuid`；
  `tests/test_d4_import_permission_gate.py` 10 passed（可见性门用真实 DB，全 ASGI 集成需真实 seed wp，故直接单元测试新增授权逻辑）。
