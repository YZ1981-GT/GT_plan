# 任务：程序裁剪 → 生成计划后续优化

需求见 requirements.md，设计见 design.md。完成项必须有代码与通过证据；隔离环境未满足的如实保留未勾选。

- [x] 0. 现状确认与设计
  - [x] 0.1 追踪两条生成端点、事务锁、文件落盘、回执和前端调用；确认无现成 generation operation/worker
  - [x] 0.2 现查 PG：ProcedureInstance 613 active、规范化重复 0；trim preview 54 consumed/71 pending；分类 NULL 15/C 3/A1 1/IPO 1
  - [x] 0.3 核对 readonly 权限/UAT 基座、GenerationPlanDialog 规模和虚拟列表依赖；完成六项 ROI 与降级裁决
  - [x] 0.4 建立 requirements/design/tasks，登记 INDEX；迁移号留到实施时动态取

- [x] 1. 两阶段生成 operation（R1）
  - [x] 1.1 动态分配迁移号；新增 operation/item ORM + V/R，状态/唯一/FK/lease/index 三层一致
  - [x] 1.2 新增 canonical request hash、所选编码 scope revision、lease claim 和 terminal receipt 幂等内核
  - [x] 1.3 抽取模板集/按编码 prepare 描述符；Phase A 锁内分流、预留 UUID、提交后零正式行/零文件
  - [x] 1.4 `wp_template_init_service` / `wp_generate_file` 支持受控 staging 路径、模板 fingerprint、manifest/hash 与精确清理
  - [x] 1.5 锁外物化；模板集 atomic 与按编码 per-item 失败语义保持不变
  - [x] 1.6 Phase B 再鉴权/项目状态/scope CAS/replan，建正式行、同卷提升、dataset/表头/parsed_data 和恢复补偿
  - [x] 1.7 两个 POST 接 operation id；新增项目归属状态 GET；契约/OpenAPI/router registry 同步
  - [x] 1.8 前端 operation sessionStorage、网络错误查询/轮询/同 id 恢复、epoch 隔离和中文状态提示
  - [x] 1.9 PG 并发、锁时长、response lost、payload 冲突、六个崩溃窗口、路径越界与回执逐字段测试

- [x] 2. active 程序行唯一约束（R2）
  - [x] 2.1 新增 `normalize_procedure_identity`，统一 init/supplement/custom/custom-with-template/trim/resolver 写读边界
  - [x] 2.2 V/R 增加冲突预检、canonical CHECK 和 active 表达式部分唯一索引；ORM 索引说明同步
  - [x] 2.3 唯一冲突映射稳定 409；初始化并发冲突重读为幂等，保留项目咨询锁
  - [x] 2.4 `delete_custom` 同时写 deleted_at，编号仍不复用；PG 大小写/空白/软删/两会话测试

- [x] 3. 粗裁确认当前态投影（R3）
  - [x] 3.1 新增 confirmation ORM + V/R：项目/循环主键、source preview、revision/hash、actor/time/request（勘误：独立为 V218/R218，见 design §3.2 补）
  - [x] 3.2 trim apply 成功事务内按 scope cycle upsert；no-op 保存更新，row-only 不更新
  - [x] 3.3 从 consumed preview 按 `(consumed_at,id)` 幂等回填；旧 scheme/history 不猜测
  - [x] 3.4 旧扫描与投影全量对拍后切换 `load_cycle_confirmations`；正常请求禁止扫描 JSON 历史
  - [x] 3.5 回滚、并发 apply、同时间平局、损坏旧 JSON、actor 降级与查询计划测试

- [x] 4. 质控分类与业务场景拆分（R4）
  - [x] 4.1 新增 ProjectClassification resolver；category/group/defaulted/scenario/资本市场 flags 单一计算（另加适用性 tags，见 design §4 补记）
  - [x] 4.2 V/R 备份并迁移 legacy IPO/refinancing 到 scenario，合法分类保留、NULL 不填 C；约束登记值（共享库已被别的进程执行，见 design §4 补记）
  - [x] 4.3 BasicInfo/Project response/wizard service/store 表单收返 category + scenario；保存刷新逐值一致（接口层 TestClient 回读；浏览器回读在 4.6）
  - [x] 4.4 UI 区分报告模板类型、质控业务分类、专项场景；IPO 项目只建议不暗改
  - [x] 4.5 生成/模板/本次触达 IPO 判断改用 resolver；客户端分类 query 下线；旧直读 AST 棘轮只许减少（后端 + 前端各一道）
  - [x] 4.6 分类 × 场景 × project/template type 矩阵、迁移/R 冲突保护、API 422 与浏览器回读测试

- [ ] 5. 只读 UAT 安全基座（R5）
  - [x] 5.1 `provision_readonly_uat_user.py`：dry-run、双确认 apply、环境/交互密码、幂等创建与精确 revoke（另加 `--scope-cycles`，见 design §5 补记）
  - [x] 5.2 工具拒绝角色/权限升级、删除/归档项目和确认错配；事务失败零部分写，零 Staff/Assignment/业务表写（PG 用例在 docker 网络内跑，原因见验收记录）
  - [x] 5.3 `usePermissionMatrix` 显式 readonly/未知角色最小权限，补正反向测试
  - [x] 5.4 独立 readonly Playwright config + BrowserContext HTTP/WS/ServiceWorker fail-closed guard
  - [ ]* 5.5 真实 UAT spec 只认显式环境变量，登录/权限/页面读/attemptedWrites/logs 双证；不自动 apply 共享库账号（代码已写、无环境变量时跳过；未实跑：需用户指定项目并放行建账号）
  - [x] 5.6 对 POST/PUT/PATCH/DELETE/beacon/popup/WS/未知 GET 做防火墙变异测试

- [x] 6. 明细性能裁决（R6）
  - [x] 6.1 建 141/250/500/1025 × 单组/多组确定性 fixture，断言 item 数和单 detail
  - [x] 6.2 Playwright 测桌面/窄屏冷热展开、Long Task、RAF 滚动、DOM；固定 workers=1/retries=0
  - [x] 6.3 连续两轮执行并记录 median/p95/max/FPS；判定 141 档是否越硬门（实跑四轮，见验收记录）
  - [x] 6.4 达标则冻结“不虚拟化”与容量曲线；超标才实现阈值化明细 virtual-list 并复测（141 档没有连续两轮超门 ⇒ 不实施）

- [ ] 7. 全链验证与收尾
  - [x] 7.1 后端聚焦 + 相关回归与 HEAD 失败集合对照；PG 临时 schema 迁移/回滚/并发
  - [x] 7.2 前端 vitest、scoped vue-tsc、ESLint；OpenAPI / JSON Schema / 路由挂载（全量 vitest 抓到 vitest 收进 `e2e-readonly/`，已排除并加守卫，见验收记录）
  - [x] 7.3 磁盘变异逐条红在预期断言，恢复 SHA-256；DB/文件故障注入不替换生产函数
  - [ ]* 7.4 【测试】项目浏览器完成 operation 正常/重放/stale；真实项目只经 readonly guard 走读（【测试】项目的正常 / 响应丢失重放 / stale 三条已实测通过；真实项目只读走读未做：需用户指定项目并放行建账号，同 5.5）
  - [x] 7.5 对账并清理 staging、operation 测试数据、UAT 专用成员、临时 schema/worktree/配置
  - [x] 7.6 更新本 spec 验收、INDEX、memory；诚实登记外部依赖和未提交/未推送状态

## 验收记录

**2026-10-29（未提交、未推送）**

- 后端：R1~R5 聚焦用例 244 passed（含 PG：operation 并发 / 锁时长 / 响应丢失 / 六个崩溃窗口、身份约束、确认投影对拍、V219 矩阵与 R219、只读账号工具）；契约 / OpenAPI / 路由挂载 76 passed，`export_procedure_chain_openapi.py --check` 一致。相关回归 161 个文件 72 failed / 3682 passed / 40 skipped / 5 xfailed，与 HEAD 干净检出逐条对比只多 3 条，都不是本 spec 引起的：golden digest 2 条（两个契约文件在主工作树里是 CRLF，本 spec 未改，按 LF 归一后与基线一致）、task70 S6 1 条（并发会话改了 workpaper_sync，工作树登记 18 个 entry，HEAD 为 0）。
- PG：V216~V219 与 R216~R219 都在临时 schema 里验证（正向、回滚、幂等、fail-closed、约束按本表 `conrelid` 判定）。期间宿主连 5432 一度在握手中被断开（`ConnectionDoesNotExistError`，容器网络内正常），那段时间的 PG 用例改在 docker 网络内的后端镜像里跑；另一时段别的会话的 pytest 占满连接（190+ 个 idle in transaction），该进程结束后恢复。断连那次运行留下 2 个临时 schema（`tgfo_v219_*`、`tgfo_v219f_*`），收尾时按前缀删除，库里已无 `tgfo_` schema。
- 共享库迁移现状：V218 是本会话 `run_pending()` 应用的（投影对拍 15/15）；V216 / V217 / V219 是别的进程启动应用时执行的（design §3.2、§4 补记）。V219 改了真实项目「重庆和平药房连锁有限责任公司_2025」的分类（IPO→NULL）与场景（normal→ipo），判定不变；备份表在库，可用 R219 回退。
- 前端：全量 vitest 2757 个文件 / 40146 例，190 例失败、71 个文件。其中 2 个文件是本 spec 引起的：`e2e-readonly/*.spec.ts` 被 vitest 收进来（exclude 没有这个新目录）⇒ `vitest.config.ts` 加 `e2e-readonly/**`，新增守卫 `src/__tests__/playwrightDirsExcludedFromVitest.spec.ts`（每个 `playwright*.config.ts` 的字面量 testDir 都必须在 exclude 里）。其余 69 个文件在 HEAD 干净检出复跑，只有 4 个比 HEAD 多失败，都与本 spec 无关（并发会话未提交的 AttachVoucherToWpDialog / renderConfigSharedHtml、HEAD 没有的 d2TbReconciliationBasis 用例、b23 PBT 随机多红 1 条且该文件在 HEAD 已红 29/30）。按关键字筛出的 29 个相关测试文件（权限矩阵、分类、向导、生成计划、粗裁等）全部通过，新守卫 3 例通过。scoped vue-tsc 只剩预存错误（注入 TS2322 能报出）；ESLint 0 error；e2e / perf / readonly 配置类型检查干净。
- 变异 15 条全部红在预期用例：后端 M1~M11 在副本里做（M9~M11 首轮因副本环境全红不算数，先跑基线 15 passed 再重跑）；前端 M12~M13 原地变异后按 SHA-256 恢复；M14（新增 Playwright 目录未排除）/ M15（testDir 写成变量）用临时配置文件打红后删除。
- 浏览器（【测试】项目、自起无头浏览器、admin，console error 0）：①R4 向导 A / IPO 读回 → 改 B / 再融资保存 → 刷新后界面与接口一致，已填细分类 A1 原样保留；②R1 响应丢失（POST 中断 1 次、状态查询 1 次）得 33 份不重复，正常再生成 26 份；③R1 stale：勾选 D / F / H / G 共 304 份，operation 到 materializing（0/304）时另经接口把 D0 粗裁为不执行 ⇒ 终态 stale、零正式底稿、零 staging，提示「程序裁剪结果已变化…」并列出被裁的 6 个编码；刷新计划后重试生成 298 份（= 304 − 6），被裁编码未生成。
- 测试数据：本轮 4 个【测试】项目（5b789b8d / 13dcf6e9 / d2229f45 / 16ca19c3，其中两个是中途失败的尝试）都经平台 `DELETE /api/projects/{id}` 软删；operation 行（2 + 2 条）与已生成文件（59 + 298 份）随项目保留在回收站口径下，wp_storage 下没有 `.generation` 残留。共享库没有建任何只读 UAT 账号。
- 性能（R6）：四轮实测见 design §6 补记，141 档没有连续两轮超门，不实施虚拟化。
- 未做：5.5 / 7.4 的真实项目只读走查（需要用户指定项目并放行在共享库建只读账号）。

> **2026-10-30 同步勘误（改号）**：本 spec 的 `V216__workpaper_generation_operations.sql` 与 `V217__procedure_identity_and_trim_confirmation.sql`（及 R216 / R217）与远端已推送的 V216（`acnr_project_registry_lock`）/ V217（`consistency_gate_acknowledgements`）撞号，同步时改为 **V224 / V225**（R 同号；内容不改、checksum 不变；共享库 schema_version 的 216 / 217 行同步改登记为 224 / 225，`migration_drift_ledger` 的 V217 漂移登记改为 225）。V218 / V219 不变。上文与 design 里的「V216」「V217」分别指现在的 V224 / V225；备份表名 `procedure_instance_identity_v217_backup` 与测试辅助里的 `V217_*` 标识符沿用旧名。
