# 实施计划：S3　写入方归属与过期状态机（formula-writer-ownership-and-stale）

> 以 design.md 为准，需求编号 R1~R4 见 design 页头。第一段（任务 0~5）不依赖拍板，可先做；第二段（任务 6）在 design §4 D1 拍板后做。
> 通用纪律：临时产物放仓库根 `tmp_writer_ownership/`；真 PG 写入只在回滚事务内的【测试】项目；标完成须有代码 + 测试 + 至少一条磁盘变异（单独一条命令跑，sha256 还原核对）；提交前在干净 worktree 跑要提交的树，失败集合与基线 HEAD 对比，只候选红 = 0；推送用 `.git-hooks/push_version.py`。
> 前置：母 spec `formula-hub-integrity-closure` 已入库；S4 若已入库，附注域「同事务标过期」改调本 spec 的 `stale_state`（两边谁后落地谁接线）。

## 第一段　不依赖拍板

- [ ] 0. 现状复核
  - 重算 design §1 六行（真库过期行与来源、全部过期写入点与清除点、清过期条件、附注写入方、试算平衡表读写字段、宽放行写请求精确清单 —— 用 TypeScript 编译器 API 现算，不用就近匹配），变化追加到 design §1 末尾
  - Verify: 探针与清单存 `tmp_writer_ownership/baseline/`

- [ ] 1. 过期状态机单一写入口（R2，ADR-WOS-01）
  - 新建 `backend/app/services/stale_state.py`（以 `disclosure_stale_marker.mark_sections_stale` 为底子，`StaleSource` 枚举含中文含义）；§1 第 1 行 14 处写入点与任务 0 现算的清除点全部改调；`note_stale_service` 两个无调用方的方法删除（删前 grep 0 调用方，单独提交）；AST + SQL 文本守卫
  - Verify: 单元；回滚事务 PG（调整分录审批事件后 `stale_source = 'adjustment'`，回滚 / 合并下级变更 / 公式设置变更各一条）；守卫违规样本自检。变异：任一批量标记恢复只置 `is_stale` ⇒ 守卫红

- [ ] 2. 重算成功即清过期（R2，ADR-WOS-02）
  - 刷新绑定、从底稿拉取、附注执行器回写三个入口按「计算成功」清过期；返回体 `changed` / `recomputed`；失败原因写 `_stale_reason`
  - Verify: 回滚事务 PG（值未变 ⇒ 清过期且计 `recomputed`；失败 ⇒ 保留并有原因）。变异：改回「有格变化才清」⇒ 用例红

- [ ] 3. 附注写入方登记表与冻结（R1 第一段，ADR-WOS-03）
  - 新建 `backend/app/services/note_writers.py`；AST 守卫（写入函数必须登记、条目真实存在）；前端 builder 数量冻结复用既有守卫
  - Verify: 守卫全绿；违规样本（新增一个未登记的写入函数）⇒ 红

- [ ] 4. 试算平衡表手工值读回（R3，ADR-WOS-05）
  - `TrialBalance.vue` 读 `content.rows`、保存去宽放行、保存后重载核对；后端端点测试断言读回
  - Verify: vitest（读回、失败不提示成功、重载核对不一致提示）；后端端点用例。变异：读回改回 `saved.data.rows` ⇒ vitest 红

- [ ] 5. 写请求按状态码判成功（R4，ADR-WOS-06）
  - 按任务 0 的精确清单逐处改；`writeRequestValidateStatusGuard.spec.ts`
  - Verify: 守卫全绿且带违规样本自检；受影响组件的既有 vitest 全绿；单区域 vue-tsc 0 错误（注入一处类型错误能报出）。变异：任一写请求加回 `s < 600` ⇒ 守卫红

## 第二段　拍板后

- [ ] 6. 唯一写方强制（R1 第二段，ADR-WOS-04，design §4 D1）
  - 按拍板结论把登记表扩成「章节 × 字段」矩阵；写入函数写前查矩阵、非所有者跳过并记日志；手工保存与锁定格不受限；前后端对拍守卫
  - Verify: 按拍板结论设计的用例（每个被限制的写入方各一条「被拒写入、其他字段照写」）；未拍板前保持 `[ ]`，写明「依赖附注权威源拍板」

- [ ] 7. 回归、浏览器实测与收尾
  - 候选树 vs 基线 HEAD 失败集合对比；浏览器（chrome-devtools，【测试】项目）：试算平衡表手工改值保存 → 刷新页面 → 值与断开标记仍在；附注过期提示显示来源；截图放 `tmp_writer_ownership/screenshots/`，用完停 about:blank
  - INDEX.md 本行与 memory.md 任务状态
  - Verify: 只候选红 = 0；推送带版本号与主要变动
