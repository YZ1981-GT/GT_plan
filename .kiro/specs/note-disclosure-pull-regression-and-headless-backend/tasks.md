# 附注取数回归修复与披露 builder 后端化 — 任务

> 以 requirements.md / design.md 为准。临时产物放仓库根 `tmp_note_pull_doc/`。
> 标完成必须有：真实代码 + 测试通过 + 至少一条磁盘变异打红（红在本判据自己的用例上）+ 生产调用方 / 挂载证据；
> 回归修复另需「由红转绿」的前后对比。共享库写操作一律先经用户放行。
> 批 1 = 任务 1~4、4a、4b、7、8a、14；批 2 = 任务 5 / 6；批 3 = 任务 10~13；真库验证批 = 13b、8 余项、9（含期间发现的
> 三处修复）。各批已推送，版本号见推送标签。

## A. 验证面解阻

- [x] 1. 测试基座走包导入全部模型 + `app.models` 注册资产模型（R2.4，design §3.5）
  - HEAD 本选集 19 个 ERROR 全是 `attachment_versions.blob_id → asset_blobs`；候选 0 个。
  - Verify：变异 M01（两处同时撤回）复现 ERROR。

## B. HEAD 回归（R2，裁定③）

- [x] 4a. 定位根因并三方恢复覆盖丢失的改动（R2.0，design §3.0 / §3.1）
  - 根因：`03496b1f3`（合并提交取了旧基线一侧）与 `85caab386`（陈旧工作区整树提交：18 个整文件回退、12 个删除）。
  - `restore_plan.py`：候选 214 个文件，会改变 HEAD 的 51 个，冲突 11 个逐条裁决；两步合并互相回退的
    `propagation.py` / `consol_note_formula_service.py` 按块一次恢复；`ConsolidationIndex.vue` 撤回。
  - 恢复链之外的丢失只登记（design §3.9）。

- [x] 2. 比例 / 损失率预设公式（R2.1，design §3.2）
  - `_ratio_presets` 按 `2de9f17aa` 恢复；执行侧求值前先查 `requires`（新用例 `test_ratio_with_blank_numerator_is_skipped_not_written_as_zero`）。
  - Verify：变异 M10（不生成比例预设）红在 `test_bad_debt_table_presets`；M08'（执行时不看 requires）红在新用例。
    M08 首轮红在基线本来就红的 `test_s5_cell_sources` 上，不算数，已点名复跑。

- [x] 3. 推送提交后附注公式收口到提交边界（R2.2，design §3.3，ADR-NPR-08）
  - 四个调用方不再各自调 `recalc_pushed_notes`；`run_and_commit(skip_note_followup=…)` 转发开关；刷新链路传
    `skip_note_followup=True`（修 HEAD 上的 `TypeError: unexpected keyword '_skip_note_followup'`）。
  - 推送拥有格：写入包保存点、`kept_push` 状态、启发式排除拥有格（用户公式可覆盖，R20.3）；守卫只认生效规则。
  - Verify：M04 / M05 / M06 / M07 / M09 / M18 全红。

- [x] 4. 合并附注种子根因（R2.3，design §3.4，ADR-NPR-09）
  - 2026-11-01 的 `net is None` 假设不成立。`unexpandable` 是 S9 拓扑序之后的过期用例（恢复为前向 / 循环两条）；
    种子计数变化唯一来自 `07bbbc4e1` 去掉交易性金融负债父行的科目 2101（国企 41→40、上市 123→122 行带科目码）。
  - `SEED_COUNTS` 改 soe (3,5) / listed (4,6)，注释逐格写明依据 + 钉死断言。
  - Verify：两条种子计数用例与两条拓扑序用例绿；变异 M15（父行恢复 2101）红。

- [x] 4b. 阻碍验证面的 HEAD 缺陷（R2.5，design §3.6 / §3.7 / §3.8）
  - 单体报表运行写 V246 共享表口径（`building` / `succeeded`、整数 `calc_version`、`error` 列，`run_display_status`
    读时换算）；真库回滚探针：HEAD DataError，候选 258 行全带 run_id 与溯源。变异 M11 / M12 / M13 红。
  - 推送测试环境补建调整财务处理表，41 个推送用例恢复。变异 M14 红。
  - 公式管理弹窗打开流程监听移到 `<script setup>` 末尾并保留 `immediate`（修 TDZ），新增「挂载即打开」两条用例。
    变异 M22（去 immediate）/ M23（注册回中段）红；vitest 未处理错误 22 → 0。
  - 子树汇总传合并表头：补 `test_ratio_columns_follow_the_consolidated_header_not_the_children`，M20 首轮存活、M20' 红。
  - 全量回归删 index（design §3.7a）：`candidate_tree_identity.cmd_build` 安全校验移出 `try`，用例补真实 index
    逐字节不变断言；变异（校验放回 `try`）须红。
  - 其余随恢复带回的改动（`note_total_push` / `orphan_states` / 批量定位底稿 / 多章节公式批量读 / 合并附注传播走
    `request_operation`）：M16 / M17 / M19 红。
  - 跨域恢复（design §3.8 表）：启动注册三个常驻 worker 与证据门禁规则、迁移就绪核验阻断启动（`test_release_migration_readiness`
    3 条 HEAD 红 → 候选绿）、用户公式 v2 实验接口 410、反向索引 Redis 导入、outbox 过期引擎。
  - 行数门（design §3.8a）：后端 4 个文件抽伴生模块（原样搬移、原名导入）+ 1 个用例文件拆出；两个前端文件 HEAD 即超限，
    按惯例登记当前行数与拆分方向。

## C. 权威源固化与门禁修真（R3，裁定①，批 2）

- [x] 5. Word 同步门禁修真 + 反向断言（R3.2，design §4.2）
  - 各 phase 一律改内存副本（`json.loads` 新读），只有写盘看 `--check`；漂移时 `report_changed_sections()` 按章节点名。
  - 门禁修真后暴露 Phase 6（单体 text_after 按位置对 Word）在现有数据上会改 81 / 116 张表（拆表后整体错位）⇒ 退役。
  - Verify：现有数据 `--check` exit 0；种子丢一张 Word 里有的表 ⇒ exit 2 并点名（`test_sync_note_templates_check_gate.py`
    4 例）；变异 T5-M1（Phase 2 照旧传 dry_run）/ T5-M2'（Phase 6 仍改模板）/ T5-M3（不点名）全红（T5-M2 首轮只改第一个
    章节、而它没有表 ⇒ 变异什么都没改，GREEN 不算数，改写后红）。生产调用方：CI `governance-checks.yml` 的
    「Check note template sync」步骤。

- [x] 6. 白名单可解释声明 + 表名判据（R3.3 / R3.4，design §4.3 / §4.4）
  - Word 白名单 689 条按证据现算类别（`note_word_allowlist`）：workpaper_authority 482 / todo 198 / word_placeholder 7 /
    user_decision 2；应收账款族 132 条全部有底稿配对证据；todo 守卫钉住只许减少；缺类别 / 理由即报错；手工条目核出处原话。
  - 表名判据：已配对单元首表比过 381 张，33 张不一致逐条登记 `names`（synonym 13 / workpaper_no_name 10 /
    workpaper_placeholder 5 / workpaper_typo 2 / todo 3）；比过张数钉住，配对退化或候选表名抽不到即红。
  - Verify：变异 T6-M1~M12 全红、各红在本判据的用例上，其中「加一条无理由条目」（M7 Word / M10 names）与「改一个
    模板表名」（M11：上市 五、1 t0 货币资金 → 受限制的货币资金）即任务原定的两条。生产调用方：
    `check_note_template_word_tree.py --check`、`gen_note_word_table_allowlist.py --check`，守卫
    `test_note_template_word_tree_alignment` / `test_note_template_workpaper_alignment`（CI backend-tests）。

## D. 共享库迁移（R1，裁定②）

- [x] 7. 迁移执行前置与方案确认
  - 现扫：13 个已由其他进程于 11-03 13:48 执行，V236 / V248 / V249 失败留在 `schema_migration_failures`。
  - 用户 2026-11-03 放行方案甲（「按建议来，开干」）。

- [x] 8a. 迁移执行器分句修复（R1.5 / R1.6，design §2.2，ADR-NPR-06）
  - 去开头 BOM；字符串字面量 / 引号标识符里的分号不分句。新用例 + 既有执行器用例 52 passed。
  - Verify：变异 M02（不去 BOM）/ M03（不认单引号）各红在自己的用例上。

- [x] 8. 执行迁移并逐项验证（design §2.3）
  - `run_pending()` 执行 236 / 248 / 249，失败 0；目标列 / 表由无变有；checksum 与磁盘一致；`schema_version` 247 → 250；
    `schema_migration_failures` 残留 0；备份 `backup_schema_version_20261103_232405.json`。
  - 2026-11-04 余项（候选后端连共享库）：`/api/health` 启动报告 45 项、失败 0、pending 0；V248 推送状态来源 34/34 由真实推送写入；
    V249 附注公式运行记录 17 条（首跑即暴露 kept_push 缺陷，见任务 13b）；V247 明细映射拉数 / 按公式填入两条路径写出
    `source_mode` + `source_digest`，子树汇总在现有【测试】数据上跑不到（乙没有单体附注），只由既有用例覆盖；V235 无执行前快照，
    改核不变量：列 / 约束 / 唯一索引齐全，存量 0 条违反，任务 9 实际走了 `content_revision` 与复核任务表。

- [x] 9. 推送→附注端到端真 PG 验证（design §5.4）
  - 【测试】公式同步甲：AJE 借 1002 / 贷 2241 各 10 → 测试经理复核通过 → 试算表 1002 审定 200 → 210 → 事件推送 → 底稿 E1 三格
    （大厅调整 0 → 10、审定合计 0 → 10、试算金额 350 → 360）→ 附注 五、1 银行存款 / 合计随推送更新、附注公式运行记录落库；
    再跑离屏刷新得试算表口径 210 / 50 / 360。撤回 → 删除 → 刷新后三层逐值回到写入前；残留逐项登记（design §5.4）。
  - 期间发现并修复：重生成合并清空手工明细的合计、删掉 `_validation_rules`（`note_cell_merge`，变异 T13-M30~M34 红）。

## E. builder 后端化期 1（R4，裁定④，批 3）

- [x] 10. 可移植性现算（design §5.3）
  - 静态闭包扫描（注入边界 = `@/utils/http` 与 apiProxy）+ 78 个 provider 在 Node 里对真实后端实跑（只读取数，写请求全部拦下）。
  - 不加垫片 76/78；F2 / F3 在 setup 里往 `window` 挂事件监听。加只在本进程内转发的 EventTarget 垫片后 78/78，其余 76 个两次
    结果逐字节相同。70 个 provider 产出 73 条载荷，写请求只有 `sync-from-workpaper` 71 / `sync-batch-from-workpaper` 2。
  - 静态判 blocker 的 21 个都是闭包里有 element-plus（composable 的提示框），实跑都没走到；无法剥离 0。
  - 产物：`tmp_note_pull_doc/provider_portability.json`（静态扫描 + 实跑结果合并）。
- [x] 11. Node 执行器骨架 + 取数注入（design §5.2）
  - `audit-platform/frontend/tools/headless-disclosure/`：`vite build --ssr`，构建别名只换 `@/utils/http` → `nodeHttp.ts`；
    `entry.ts`（bootstrap / runProvider / refreshNotes，复用 `HEADLESS_PROVIDERS` 与 `runHeadlessDisclosure`）；`run.mjs`
    （probe / capture / refresh）。源码不为 Node 改一行。
- [x] 12. D2 + E1 浏览器载荷 vs Node 载荷 canonical JSON 相等（design §5.3 表）
  - 真实 Chromium（Vite 开发服务、真实 axios）vs Node：三组有载荷的逐字节相同，第四组两侧都 0 条。
  - Verify：变异（Node 侧 D2 翻转 variant）⇒ 不相等、退出 1，只红在两条 D2 上。
- [x] 13. 手工触发端点 + 命令行 + 保护用例（design §5.4）
  - 端点 `POST /api/disclosure-notes/{project_id}/{year}/headless-refresh`（附注编辑门禁，清册覆盖集合 +1、配方 C1 五种身份）；
    命令行 `backend/scripts/ops/note_headless_refresh.py`；服务 `note_headless_refresh_service`（触发人本人的 6 分钟令牌只经 env、
    env 从零构造、只连环回、项目年度互斥、超时 / 断开终止进程树、跑完吊销）。
  - 执行器加固：写请求名单（五个现有端点、限本次项目 / 年度 / 章节，`allowWrite` 必填）；构建清单逐文件 sha256 核对，过期拒绝运行。
  - 保护：执行器真实载荷（D2@【测试】公式同步甲）过整章 `_manual_override` / 正文 `is_local_override`（带对照组）/ 推送 ownership
    重放；全部与单章节重算都 `skip_manual=True`；首次同步保护在执行器侧由前端用例钉住。
  - 用例：后端 `test_note_headless_refresh_service.py` 20 条 + `test_note_headless_refresh_protections.py` 6 条；前端
    `tools/headless-disclosure/executor.spec.ts` 11 条（CI `npm run test:unit` 收集）。
  - Verify：变异 T13-M1~M24 全红，各红在本判据的用例上（M4 首轮把用例挂死、手工终止不算数，用例改限时等待后复跑红；
    前端各条按失败用例名核对，无套件级报错）。
  - 顺带：附注写端点清册随 HEAD 现状重生成（`note_templates.py` 4 个端点 I → X、`validate` 补登录，是
    formula-management-residual-closure 改门禁后没重生成，`test_authz_inventories_check_mode` 在 HEAD 即红）。
- [x] 13b. 【测试】项目真实写库跑通「不开页面也更新」（R4.6，用户 2026-11-04 放行；design §5.4）
  - 候选后端（`GT_BOOTSTRAP_DONE=1` 不跑迁移、`GT_NEVER_PRIMARY=1` 不跑常驻任务）上调端点，环境等价先核：同一执行器对 D2@甲 只读
    取数，9985 与 9980 载荷逐字节相同、与任务 12 的 sha 相同。端点 1.5~3 秒跑完：D2 → 五、5 被首次同步保护挡下（已有 2 格人工填写），
    推送保留人工格 库存现金；底稿 / 试算表零写入。
  - 跑前修：Windows 开发服务器的 Selector 事件循环不支持 asyncio 子进程（端点恒 500），改线程拉起 + 线程等待，新增两例真子进程
    用例（变异 T13-M25~M28 红）。首跑暴露并修：推送拥有格的 `kept_push` 原样进来源信封 ⇒ ValidationError、整节附注公式回滚
    （变异 T13-M29 红）。

## F. 回归与收尾

- [x] 14. 候选树回归（批 1，design §6）
  - 后端选集 candidate-only red 0（修好 84，两边都红 77）；前端 candidate-only 3 条全是 PBT 种子红、同种子在 HEAD 同样红；
    未处理错误 0 / 0；全量 `vue-tsc` added 0（2969 → 2964）；变异 24 条全红（含 M24：候选树工具的安全校验放回 `try`）。
  - 后端全量（73557 节点）：candidate-only red 13 条逐条单跑，12 条绿（index 被删窗口 / 负载），1 条 PBT 反例在 HEAD
    同输入同样失败；修好 1343（1202 条是 `asset_blobs` 外键找不到表）。
  - 推送前若远端前移：三方合并到新头后重跑受影响用例。

- [x] 15. 文档与收尾
  - 批 1 的 INDEX / memory 随本次推送更新；批 2 / 3 完成后再收尾、清理 `tmp_note_pull_doc/`（保留证据摘要）。
  - 2026-11-07 完成：`tmp_note_pull_doc/` 目录已不存在（早已清理）；INDEX.md 状态由 18/19 更新为 19/19 ✅。

## 待用户决策

| # | 决策 | 阻塞 |
|---|---|---|
| D2 | R4 期 1 若可移植性证明失败，是否接受 C 路线（无头浏览器）作过渡 | 任务 10 之后（已证可移植，不需要） |
| D4 | 恢复链之外的 8 个文件（design §3.9）是否交归属方逐个复核恢复 | 不阻塞本 spec |
| D5 | 任务 8 余项与任务 9 需要在【测试】项目上写库验证，何时放行 | 已放行并执行（2026-11-04） |
| D6 | 【测试】公式同步甲 83 节被重并删掉的 `_validation_rules` 是否按模板重新注入（只能直接调服务写，没有平台入口） | 不阻塞 |
| D7 | 主工作树 42 个「等于某历史提交原样副本」的已修改文件是否恢复成 HEAD 版（含本链路的 formula_push 三个文件与 `note_formula_generator.py`：主实例 9980 事件推送因此恒 TypeError，本批 `kept` 修复在主实例上也未生效，design §9.1） | 不阻塞本 spec |
