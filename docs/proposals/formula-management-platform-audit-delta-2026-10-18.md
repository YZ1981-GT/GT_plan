> 基线：`formula-management-platform-audit-2026-10-17.md`。原报告保留为快照，本文件只记录实施后变化与残余风险。

## 一、当前结论

截至 2026-10-18，原审计指出的公式项目鉴权、执行器静默 0、非原子 CAS、standalone mutation 空转、synthetic capability 与非阻断浏览器门禁已经完成主路径整改。复核期间又发现并修复了 dirty 会话目标漂移、fresh DB 无测试数据、runtime 丢失 `confirm_overwrite`/DraftMarker/preset、rollback 值方向反转、冲突仍 commit、outbox 只写不消费，以及 formula_push PG 测试跨 loop 未 dispose 的问题。

功能闭环已有 TestClient、真实 PG、Vitest 和 Playwright 证据；但 spec 仍保持 active（29/30），原因是 `FormulaManagerDialog.vue` 单文件 `vue-tsc` 在 4GB 堆 OOM，此前 8GB 区域检查亦 OOM。该项没有假标完成。

## 二、原 finding 状态

| 原 finding | 当前状态 | 当前证据 | 残余 |
|---|---|---|---|
| FM-P0-01 sheet 串页 | 已闭合主路径 | 结构化精确匹配 + 当前页 renderer 测试 | 全宿主覆盖由快速 inventory 守卫承担 |
| FM-P0-02 surfaced/保存错域 | 已闭合 | kind 分派、wp CAS、pinnedLocation 保存 | 无 |
| FM-P0-03 node-only / 上下文漂移 | 已闭合 | 真实 canonical helper；dirty owner/pending reducer；合并 scope facade | 无 |
| FM-P0-04 附注用户公式 | 原 spec 已闭合定义消费 | 用户集覆盖模板并统一拓扑 | report/note runtime canonical binding 仍不得猜写，属后续扩域 |
| FM-P0-05 项目隔离 | 已闭合本审计旁路 | formula batch/report execute/list/types/seed 403/422 与零副作用 | 仓库其他域项目隔离基线不在本 spec |
| P1 函数支持 | 已闭合 | 后端 preflight 覆盖单/批入口；report strict context | 未注入上下文的函数明确拒绝，不再返回 0 |
| P1 standalone 空转 | A1 安全 canary 已闭合 | 目标值、snapshot、audit、outbox、last_computed_at 同 run_id PG 对拍 | 结构化 checklist/report/note 需显式 binding 后再扩域 |
| P1 覆盖/回滚治理 | 复核新增并已闭合 | human_edited 未确认跳过；确认覆盖后公开 rollback 逐值复原 | 无 |
| P2 门禁 | 已闭合 blocking 代表矩阵 | fresh seed + A1/D2-1 + 合并三 scope Playwright 3/3 | 全量 Vue 类型检查仍 OOM |

## 三、关键实施裁决

1. **CAS**：已有公式缺 `expected_version` 返回 428；更新使用 `UPDATE ... WHERE definition_version=:expected RETURNING`。拒绝 `SELECT → Python 比较 → flush`。
2. **写入范围**：当前只对可证明载体的 A1 `WorkingPaper.parsed_data` 构造 runtime target。结构化 checklist/report/note 缺 binding 时可见失败，禁止用 `sheet_name` 猜 `item_id`。
3. **事务 owner**：`execute_refresh` 统一拥有业务写、snapshot、公式状态、DraftMarker/preset marker、哈希审计和 outbox；preset 没有 canonical binding 时只登记待编制，不计 applied。
4. **覆盖策略**：`confirm_overwrite` 进入 fingerprint；锁键按项目+年度串行化，防确认/不确认两个 fingerprint 并发触达同一目标。
5. **回滚**：adapter 永远把 snapshot.before_value 写回，以 after_version 做 CAS。任一业务或 marker 冲突使整个 savepoint 回滚，router 不 commit 并返回 HTTP 409、restored_count=0。
6. **能力上下文**：工作底稿只能消费服务端 snapshot；项目级 report/note/tb/consolidation 走显式 scope。dirty 时完整活动 payload 固定，保存后才切 pending。
7. **Outbox**：复用现有 `outbox_replay_worker`，独立 session + `SKIP LOCKED` 重试发布；主事务同步标 stale，避免只写表无人消费。
8. **CI 数据**：`seed_fix_projects.py --fix` 不是 fresh bootstrap，已从专项 job 删除。新 seed 幂等创建可登录 admin、稳定 standalone 项目、A1/D2-1 两个有效 XLSX；合并项目仍由 `seed_consol_uat.py` 单独负责。

## 四、验收证据

- 后端目标矩阵：`163 passed`。
- 严格 PG：`5 passed`，覆盖双事务 CAS、production apply、写后故障全回滚、人工编辑策略+公开 rollback、formula_push SQL 故障隔离；`PytestUnraisableExceptionWarning` 作为错误，未再出现 `_cancel was never awaited`。
- 前端目标区域：`527 passed / 3 skipped`；skip 是显式 live-denominator 环境门，不影响 blocking 浏览器 job。
- 类型/静态：纯 session/context 契约 `vue-tsc` passed；改动文件 IDE diagnostics 0；targeted ESLint 0 error。
- 浏览器：`formula-manager-runtime-gate.spec.ts` 3/3，真实登录与网络请求，不允许后端/夹具缺失时默认 skip。
- Evidence：`.kiro/specs/formula-manager-runtime-integrity-closure/basis/runtime-evidence.json`，稳定排序、不含凭据，未提交态明确 `working_tree=true`。

## 五、未完成与非本轮红

1. `[ ]*` `FormulaManagerDialog.vue` 单文件完整 `vue-tsc`：`NODE_OPTIONS=--max-old-space-size=4096` 仍 OOM；此前 8GB 区域检查同样 OOM。不能据“stdout 无 TS error”误报通过。
2. 全 `formula_management + formula_runtime` 811 项混合套件为 `740 passed / 13 failed / 58 errors`：大量 fixture 在 drop 全 metadata 时触发历史环 FK `SAWarning` 并中止；live 404 新出现 `B5附件` 未登记。目标 163 项与 PG 5 项单独全绿。
3. 前端扩大区域中，本轮未改的 `FormulaPushPanel.spec.ts` 仍只允许 3 个 GET，而现生产面板已请求 `/runs`；该并发/预存红未越界修改。
4. `check_formula_runtime_completion.py --strict` 的旧 active 路径已归档，且并发 `note_source_resolvers.py` 新增低级求值导入；不属于本 spec 改动。
5. 旧 formula-history rollback 仍应另立整改：应以 config_id/完整复合键 + expected_version 复用正常传播链，禁止按 row_code `LIMIT 1`。本轮修复的是 draft-refresh runtime rollback，不混淆两条回滚语义。

## 六、完成度勘误

`formula-manager-closure` 的 30/30 只表示原条目已执行/登记。其 append-only 9.1 继续由本 spec 承接；本 spec 当前 29/30，功能关闭条件已满足，但在完整 Vue 类型检查取得可复验证据前不归档，也不把旧 spec 改写成 31/31。
