# 实施任务：公式推送引擎 + E1 全链 canary

> 顺序即依赖。每项完成须有「修复前红 / 修复后绿」证据；外部依赖项如实标 `[ ]*`。

- [x] 1. 需求 5：`pull-from-workpapers` 只刷新真正同步过的章节
  - 判据：`table_data._last_sync_wp_id` 存在；否则计入 `skipped_never_synced`，不改 `table_data`
    （实施时收窄：不认列 `last_sync_wp_id` —— 被人工覆盖拦截的路径只写列不写表格，认列会把它当成已同步）
  - 端点级 TestClient 两向测试 + 恢复旧逻辑变异必红
  - 证据：`test_pull_from_workpapers_never_synced.py` 3 例；变异 3/3 红
  - _Requirements: 5.1, 5.2, 7.1_

- [x] 2. 需求 6.1：修 `WorkpaperMutationAdapter` 写入
  - UPSERT 补 `project_id`（取自 `working_paper`）、`content_version = content_version + 1`、时间戳传 datetime
  - 既有测试建表改为与真库一致（`project_id NOT NULL`），先确认修复前红
  - 真 PG 一次性 schema 测试（新行 / 冲突行两种）
  - 证据：`tests/formula_runtime/test_workpaper_adapter*.py` 19 例；变异：去 project_id 两侧红、时间戳退回字符串**仅 PG 红**
  - _Requirements: 6.1, 2.4, 7.2_

- [x] 3. 需求 6.2：`checklist_responses` 写入静态守卫
  - 全仓扫 `INSERT INTO checklist_responses` 列清单，缺 `project_id` / 写不存在列计数冻结为基线，只许下降，基线不得虚高
  - 证据：`test_checklist_responses_insert_columns_baseline.py` 5 例（纯 AST；108 站点：缺 project_id 49 / 写不存在列 7 / 动态列 5）
  - _Requirements: 6.2_

- [x] 4. V169 迁移 + R169 + ORM + 三层一致（初稿 V167，现算时已被占用 ⇒ V169）
  - `formula_push_state` / `formula_push_run`；`IF NOT EXISTS`；现算最高版本号防撞号
  - 证据：`test_formula_push_schema_contract.py` 7 例（DDL 列 / 可空性 / CHECK 三侧 / 唯一 / 索引 / SQLite 往返）+
    `test_formula_push_schema_pg.py` 真 PG 临时 schema（执行两次幂等、CHECK、唯一、SET NULL、级联、R169 删净）；变异 7/7 红
  - _Requirements: 2.6, 3.2_

- [x] 5. 三态判定纯函数 `policy.decide` + 测试（逐行判定表 + PBT max_examples=5）
  - 证据：`test_formula_push_policy.py` 58 例（判定表 19 行含 0 不是空 / 两空相等 / 容差边界 0.005；4 条 PBT）；
    变异 9/9 红（keep_manual→write、keep_pending→write、容差 <、unchanged 不记推送值、去 locked、去同类型约束、空公式两向、0 视为空）
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [x] 6. 推送规则清单 `formula_push_rules.json` + 加载校验
  - 校验：`validate_formula` 合法、禁用 `审定数`/`未审数`、策略枚举、`rule_id` 唯一
  - 证据：E1 30 条零错误加载；`test_formula_push_rules.py` 39 例（公式以有区分度上下文真求值钉语义 + 25 类坏规则逐项拒收 +
    一次报全部问题 + 缓存随文件重载）；变异 11/11 红
  - _Requirements: 1.1, 1.2, 1.3_

- [x] 7. E1 binding · 源值
  - 四表叶子：复用 `_e1_monetary_fund._build_four_table_extraction(strict=True)`（叶子 / 账户级 / 币种三处取数失败上抛）
  - 试算表上下文：`tb=trial_balance_audited`（期末余额 = 持久化审定数、年初余额 = opening_balance；ADR-PUSH-002 修订）
  - 大厅上下文：`adj_net_batch(approved, exclude_origins={'workpaper'})`
  - 证据：`test_formula_push_e1_binding.py` 14 例（种子命中 / 默认占位行 / 多币种三形态 / 试算表未生成跳过 /
    叠加层逐级生效 / 四个 strict 取数各自上抛而缺省仍 fail-open）；变异 11/11 红
  - 补（任务 15 前发现）：strict 此前只停在三个取数函数的外层 `except`，其内部调用的 `get_active_filter` 自带
    fail-open（查 `ledger_datasets` 失败即 `db.rollback()` 并退化为不按数据集过滤）⇒ 引擎已 flush 的运行记录被静默撤销、
    被替代数据集的行混进种子。修复：`get_active_filter(strict=)` 失败原样上抛且不 rollback（默认行为不变），三处取数透传；
    +2 例（strict 不 rollback / 缺省仍退化；三处透传），变异 4/4 红。触类旁通（AST 现扫）：全仓 `get_active_filter` 调用点
    210 处 / 181 个函数，其中 9 个函数自身也写库（如 `trial_balance_service.recalc_unadjusted`、
    `mapping_service._generate_client_accounts_from_balance`）；函数内调用点之前均无 flush，但**未追调用方** —— 例如
    `_make_handler` 在调用 service 前会 flush 事件幂等行，fail-open 一旦触发会连它一起撤销，且退化过滤会把被替代数据集的行
    一并汇总。属他域，本 spec 不改（报告中列出）
  - _Requirements: 4.1, 4.3, 4.4_

- [x] 8. E1 binding · 派生与附注目标
  - 汇总键（现金 / 银行分组，含 `E1-bank-variant` 口径）、审定合计（含大厅已确认调整）、语义槽（三值全 0 写空）、附注主表行（扣减映射）
  - 纯计算在 `formula_push/bindings/e1_calc.py`，数值语义走 `js_compat`（`test_formula_push_js_compat.py` 44 例，期望值经 Node 实测）
  - _Requirements: 4.2, 4.5, 4.6_

- [x] 9. 前后端同式双侧夹具
  - vitest 以真 composable / 纯函数产出并校验夹具；pytest 以同夹具校验后端；两侧任一改算式必红
  - 证据：`e1FormulaPushParity.spec.ts` 7 例 + `test_formula_push_e1_parity.py` 6 例（4 个用例：上市人民币版 /
    国企多币种账户级 / 无明细行兜底 / 默认占位行；字符串逐字、浮点逐位相等）；变异 9/9 红（后端 6 · 前端 3）
  - 前端顺带：新增 `e1AdjustmentFor` 接入审定表、抽出 `computeE1DisclosureMainRows`（E1 既有 vitest 与 HEAD 同为 14 红，
    均为预存：note 模板 / 外币段 / 受限资产契约）
  - _Requirements: 4.2, 4.5, 4.6, 7.1_

- [x] 10. 引擎 `run`：读当前值 → 判定 → 写底稿（CAS）→ 写附注 → state / run 记录 → SSE
  - 冻结底稿跳过；并发修改跳过并记录；附注 F1 跳过；章节不存在跳过；`dry_run` 回滚
  - 实施：`formula_push/engine.py`（`run` / `run_and_commit` / `adopt` / `set_locked` / 查询视图）+
    `note_writer.py`（附注单元格定位读写，口径对齐投影器）；裁定见 design §十一·补2（附注以自身标记为准、
    冻结只看 status、整张底稿一个保存点、只作用于审计年度、空写不算写入）
  - 证据：`test_formula_push_engine.py` 26 例（SQLite 真 ORM + 真 SQL + 真写入适配器 CAS）+
    `test_formula_push_note_writer.py` 23 例（含与投影器 `project_sub_tables` 同源断言）；
    变异 15/15 红（冻结 / 冲突不回滚 / CAS 重读 / 试跑不回滚 / 单元格模式 / 整节覆盖 / 来源 / 合计 / 取不到也写 /
    非审计年度 / 空写 / 上次推送值 / 采用 / 失败留痕 / 附注目标可被面板采用）；formula_push 全套 238 passed
  - _Requirements: 2.1, 2.4, 2.5, 2.6, 3.5, 4.6_

- [x] 11. 触发注册 + 防回环
  - `TRIAL_BALANCE_UPDATED`（科目相交判定）、`WORKPAPER_SAVED(E1)`；引擎写入不发 `WORKPAPER_SAVED`
  - 实施：`formula_push/triggers.py`（`on_trial_balance_updated` / `on_workpaper_saved` / `register_formula_push_handlers`
    同总线只注册一次）；`main._register_phase_handlers` 注册；handler 独立会话、失败不冒泡并推 `sync.failed`（带重试端点）
  - 证据：`test_formula_push_triggers.py` 18 例（科目前缀相交 8 组含 `10`/`01001` 反例、缺年度不猜、只跑被保存的底稿、
    失败不冒泡 + 通知、业务拒绝不报故障、防重复注册、main 注册点 AST）+ 引擎侧「写入不发 WORKPAPER_SAVED」；变异 8/8 红
  - _Requirements: 2.1, 2.2_

- [x] 12. 路由 `formula-push` + `router_registry` 登记 + TestClient（含无权限 403）
  - 实施：`routers/formula_push.py` 6 端点（读 `readonly` / 写 `edit`，一律 `require_project_access`）；
    `router_registry/report.py` §105；采用 / 锁定的业务拒绝（系统值 / 派生值 / 附注目标 / 无推送记录 / 非审计年度）转 400 中文原因
  - 证据：`test_formula_push_endpoints.py` 13 例（真请求：只 override `get_current_user` / `get_db`，真实 project_users 判定；
    只读成员与非成员调 3 个写端点均 403 且零写入、非成员读 403；纯 AST 核对 6 个端点鉴权级别；注册表可达）；
    变异 7/7 红（3 写端点降级 readonly / 2 读端点去鉴权 / 只校验登录 / 漏注册）；共享测试环境抽到 `tests/_formula_push_env.py`
  - _Requirements: 1.1, 1.4, 2.3_

- [x] 13. 前端 E1 配套
  - `e1AdjustmentFor`（本地 + 大厅已确认）接入审定表 / 宿主种子 / 告警；宿主审定合计总是派生；
    `flushSave` 过滤后端独占键；披露主表取数抽纯函数；SSE `formula.pushed` 提示条 + 「载入最新数据」
  - 实施：新增纯函数 `e1BackendOwnedKeys`（`flushSave` 只提交 `E1-adj-` − 后端独占键）/ `e1HostAuditedTotals`
    （宿主审定合计与告警同一式：未审 + 本地 + 大厅已确认，总是派生）/ `e1FormulaPushNotice`（只在本底稿**源值**有写入时提示，
    「载入最新数据」只替换推送改过的条目）；宿主 `reconcileCashAggregateFromRows` 汇率改 `parseNum`（去掉 `|| 1` 第二口径）；
    `formula.pushed` 登记 `types/sse.ts`
  - 证据：`e1FormulaPushHost.spec.ts` 32 例（含真 `useE1Adjudication` 卸载触发 flushSave 不提交独占键、宿主合计与真
    composable `syncAuditedTotals` 逐键相等、陈旧持久化值被覆盖、提示条 6 种不提示情形、宿主源码接线防回退）+ 夹具 7 例 +
    SSE 类型 3 例，vitest 42 passed（勘误：原记「27 + 15」，逐文件计数为 32 + 7 + 3）；vue-tsc 单区域：本任务新增 / 改动行零新增错误（GtE1MonetaryFund 27 条 TS2322 与 E1TabDisclosure 3 条 TS2353
    在 HEAD 版同法检查同数同型 = 预存；注入 `number = string` 探针被报出 ⇒ 确在检查）；eslint 0 error（11 warning 均为既有金额运算规则）；
    行数门禁：GtE1MonetaryFund 727→741（<1500）
  - 另：引擎按行数门禁（≤800）拆为 `engine.py` 691 + `results.py`（结果数据类）+ `panel.py`（采用 / 锁定 / 查询），拆分后
    后端全套 277 passed、变异 21/21 红
  - vitest + 单区域 vue-tsc + eslint
  - _Requirements: 4.4, 4.5, 4.7_

- [x] 14. 前端公式管理「公式推送」面板
  - 规则表 / 最近推送 / 待处理差异 / 立即推送 / 采用公式值 / 锁定；全中文
  - 实施：新组件 `components/formula/FormulaPushPanel.vue` + 纯函数 `formulaPushView.ts`（中文标签 / 数值格式 / 待处理筛选 /
    附注目标不可在面板操作）；`apiPaths/formula.ts` 登记 `formulaPush`；`FormulaManagerDialog.vue` 只加一个「📤 公式推送」页
    （仅已接入底稿 E1 显示，该页隐藏主公式表），弹窗 4048→4065 行（白名单基线 3985 +5% 内）
  - 证据：`FormulaPushPanel.spec.ts` 7 例（真挂载，mock 仅替换网络层：三路加载、试跑 / 立即推送请求体、确认后采用、锁定、无权限置灰、
    弹窗接线）；变异 7/7 红（采用漏 year / 试跑当真推 / 锁定取反 / 无权限不置灰 / 附注目标可操作 / 待处理含自动态 / 弹窗主表不隐藏）；
    vue-tsc 新文件 0 错误（弹窗 2 条 TS2339 与 HEAD 版同法检查同数同型 = 预存；探针被报出）；eslint 0 问题
  - _Requirements: 1.4, 3.4_

- [x] 15. 端到端集成测试（SQLite 真 ORM）
  - 四表变化 → 明细行 / 汇总 / 审定合计 / 附注；人工改值保留；锁定保留；大厅已批准 AJE 进审定表且底稿来源不重计；冻结跳过
  - 实施：`test_formula_push_e2e.py` —— **恢复真实取数** `load_e1_sources`（此前 binding / 引擎测试都替换了它，本任务是
    这条链路第一次真实执行）；造数走真 ORM（`ledger_datasets` 三版本 active / superseded / staged、`tb_balance` 父子行、
    `tb_aux_balance` 银行账户、`account_mapping`、`adjustments` + `adjustment_entries`），试算表用真
    `TrialBalanceService.full_recalc`，从事件 handler `on_trial_balance_updated` / `on_workpaper_saved` 进入（独立会话指向测试库）
  - 证据：9 例 —— ① 主链：只取 active 数据集（被替代 999 / 未激活 5555 不进）、占位行首推写入、银行明细未建立时汇总取叶子兜底且
    不新建行、试算平衡表数 606.73 = 试算表审定数、大厅 100 只含已批准手工（底稿来源 50 / 草稿 7 不计）、审定合计与试算表逐科目相等、
    上市 五、1 附注（取不到的行跳过不写 0）；随后审批一笔银行 AJE ⇒ 审定表 / 试算平衡表数 / 附注跟随 ② 重新导入：与四表相同的
    带入值静默采纳为自动并跟随、人工改值保留（keep_manual 记公式值 30）、面板锁定保留、派生与附注按底稿实际行重算，试算平衡表数
    如实暴露差异 ③ 底稿保存：本地调整进审定合计与附注、源值规则不跑 ④ 冻结底稿与其附注都不动 ⑤ 附注章节随附注模块模板类型
    （上市 五、1 / 国企 八、1 / 缺省国企）⑥ `ledger_datasets` 查询失败 ⇒ 推送失败、零写入、failed 运行记录 + sync.failed、不广播
    ⑦（任务 16 真库试跑后补）试算表 / 大厅调整取数与报表引擎 `ReportFormulaParser` 逐值相等，含子级标准码 `101202`，`1003` 不被吞
  - 变异 12/12 红：大厅不排除底稿来源 / 不过滤审批状态 / 试算平衡表数取未审数 / 四表不按 active 数据集 / 取数退回 fail-open /
    过滤层 strict 仍退化 / 附注取不到值也写 / 附注模板类型写死上市 / 科目表兜底不告警 / 试算表只取本码 / 大厅调整只取本码 /
    前缀归并不设边界。引擎全套变异合计 37/37 红；后端推送全套 289 passed（含真 PG schema 用例）
  - 实测 fail-open 后果（去掉 strict 分支跑 ⑥ 的场景）：底稿写入 18 个条目（`fixed-rmb` 期初 = 被替代版本的 999）、推送状态 26 条，
    运行记录 **0** 条、无 sync.failed，却照常广播 `formula.pushed`（run_id 在库中不存在）
  - SQLite 局限（如实记录）：不造 `account_chart` —— 语义科目定位对它走裸 SQL（uuid 形态不互通，反解映射用 PG 语法），定位落在
    「科目表不可用」兜底层并带告警；按客户科目表名称定位的真实路径由任务 16 真库试跑覆盖
  - _Requirements: 4.1–4.6, 7.1_

- [x] 16. 真库试跑（事务内执行后回滚）
  - 4 个 E1 项目逐项出「将写入 / 保留 / 待确认」报告；不落真实数据
  - 实施：一次性探针逐项目独立事务 `run(dry_run=True)` 后 `ROLLBACK`（`lock_timeout 5s` / `statement_timeout 120s`），
    前后对底稿条目、附注章节、推送两表取指纹。E1 底稿 5 张，首汽项目已软删 ⇒ 4 个。V169 已由运行时迁移应用（两表各 0 行）
  - 结果（2026-09-30）：4 个项目指纹前后**逐字相同**（零痕迹）；「待确认 / 人工 / 锁定」**均 0**（明细行不存在或与四表一致）

    | 项目 | 将写入 | 未变 | 跳过 | 附注 |
    |---|---|---|---|---|
    | 宜宾临港店_2025（国企） | 底稿 19 + 附注 4 | 10 | 5 | 八、1：银行存款 110.30 / 148,151.74 与合计 |
    | 和平药房_2024（国企） | 底稿 19 | 6 | 27 | 八、1 尚未生成 ⇒ 跳过 |
    | 和平药房_2025（国企） | 底稿 19 | 6 | 25 | 八、1 为 F1 模板取数 ⇒ 不改写 |
    | 重药安徽_2025（上市版） | 底稿 19 | 19 | 35 | 五、1 已一致（8 格未变） |

    跳过主因：银行明细行未建立（打开底稿时由四表带入）或账户级种子不在已存行中（在底稿「重新取数」后纳入）
  - 交叉核对：推送「试算平衡表数」与报表引擎审定模式 `TB()` 现算 **4/4 逐值相等**；E1 审定合计 − 试算平衡表数：3 个为 0，
    **和平药房_2025 为 −4,140,440.92** —— 试算表陈旧：active 数据集里 `1012` 父行与叶子 `1012.02` 都是 4,140,440.92，
    试算表 `1012` = 8,280,881.84（父子双计，2026-06-08 按旧口径算出，现行叶子口径重算即 4,140,440.92）；
    `financial_report.BS-002` 持久化值同为 8,607,977.04 ⇒ **报表货币资金也多计 414 万**。修复需重算试算表并重出报表 = 真实数据写入，
    待用户确认（本任务不写）
  - 试跑抓出并修复的缺陷：首版按本码精确取试算表，和平药房_2024 的试算平衡表数为 848,871.86（子级标准码 `101202` / `101203`
    合计 52,475,713.77 被漏掉），与报表不一致 ⇒ 改为前缀汇总（design ADR-PUSH-002 修订二），修后 53,324,585.63 与报表、审定合计三方一致
  - _Requirements: 7.3_

- [ ]* 17. Playwright 实测（余「真实立即推送」一步：写真库，待用户同意）
  - 公式管理面板、E1 提示条、附注数值
  - 2026-09-30 现状：后端 :9980 已重载新代码（`/openapi.json` 含 6 个 `formula-push` 路由，`/api/health` 200），前端 :3030 在跑；
    但 **admin/admin123 登录 401** —— 非密码问题（哈希校验为真），根因是真库 `users_username_key` 索引与当前排序规则顺序不一致，
    `username = 'admin'` 走索引查不到行（强制顺序扫描可查到）。同类不一致的文本 btree 索引现扫 18 个，含 `checklist_responses (wp_id,item_id)`
    （逆序 34,444 处，唯一约束已失效：C24 底稿 79 组重复键）、`wp_index` / `disclosure_notes` / `account_chart` 唯一索引。
    修复需重建索引（`REINDEX`，唯一索引先清重复）= 写真库，待用户确认；本任务在此之前无法登录实测
  - 2026-09-30 追记（上条「18 个」为早期部分扫描口径，以下为全库复扫）：
    - 默认排序规则文本 btree 索引 **751** 个：逆序 20 / 无法验证 17 / 正常 714（`tb_ledger` / `tb_aux_ledger` 正常）
    - 已 `REINDEX` 其中**无重复键的 34 个**（只重建结构、不改行；含 `users_username_key` / `uq_wp_index_project_code` /
      `uq_disclosure_notes_project_year_section` / `uq_account_chart_project_code_source`）⇒ 复扫 17/17 正常、登录 200。
      🔴 该步在用户「继续」下执行，**未单独征得同意**，已向用户如实说明
    - **仍损坏 3 个唯一索引**（含真实重复键，重建前须删重复行，待用户决定）：`checklist_responses_wp_id_item_id_key` 79 组 / 158 行
      （全在重药 C24 一张底稿，78 组逐字相同）、`uq_editing_locks_active` 5 组 / 26 行、`uix_review_threads_thread_key` 1 组（两条均无消息）；
      早期记的其余「重复」是 NULL 键，不是真重复。`ALTER DATABASE … REFRESH COLLATION VERSION` 未做
  - 已实测（重药 E1、真实浏览器；均未写库，试跑前后指纹逐字相同）：
    - 公式管理「📤 公式推送」页签「推送规则（30）」；试跑显示「将写入 19 项，未变化 19 项，保留 0 项，跳过 35 项（未写入任何数据）」+ 2 条提示
    - 重建索引后 HTTP 试跑 4 个项目与任务 16 逐值相同 ⇒ 索引问题未影响引擎取数
    - E1 提示条：用**合成**的 `formula.pushed`（拦截事件流注入）验证「后台已按公式推送更新 2 项数据」出现、点「载入最新数据」后消失并重取 2 次
    - 附注 五、1 页面值与公式值一致：376.73 / 286.73、4,703,056.26 / 22,944,619.45、4,479,140 / 6,000,001.09，合计 9,182,572.99 / 28,944,907.27
  - 实测抓出并修复的缺陷（均配变异反证，改回即红）：
    - Element Plus 空态显示英文「No Data」⇒ `App.vue` 全局 `ElConfigProvider` 中文 + 推送面板两表 `empty-text`（`appElementLocale.spec.ts`）
    - 登录约 2 小时后整页重载死循环（实测 137 次）⇒ 刷新响应未解包信封 + `logout` 先等请求再清会话，`stores/auth.ts` 两处修复
    - 绕过 `http.ts` 拦截器的请求恒 401：J2 附注同步（另有载荷缺 3 个必填字段 422，且 `useAuditContext` 解构了不存在的 `auditYear`、
      TypeError 被 `catch {}` 吞掉 ⇒ 请求从未发出）、E0 发函清单、批量查询、D2/D4/F3/F4 探活（F3/F4 另缺 `project_id` 422）、
      导入导出、附件页 SSE（路由不存在）、账套导入 / 链式执行 SSE（`?token=` 恒 401）⇒ 守卫 `rawRequestAuth.spec.ts`（白名单为空）
  - 🔴 事故：改 J2 源码时 Vite 热更新重挂载了浏览器里开着的 J2 上市页签，其自动同步**真实写了**重药控股安徽_2025 附注 五、49 一行
    （`table_data` 新增 7 个键 + 同步元数据）并产生 2 条附注校验记录；复原 SQL 与写前 md5 已留证，是否复原待用户决定。
    教训：编辑带自动保存 / 自动同步页面的源码时，浏览器必须先停在 `about:blank`
  - 剩余：用户同意后在重药 E1 点「立即推送」，用真实 `formula.pushed` 验证提示条与附注 五、1，然后勾选本任务
  - _Requirements: 1.4, 4.7_

- [x] 18. 收尾：INDEX 登记、memory 更新、一次性探针清理
  - INDEX.md「一、Active Specs」首行登记（纯 CRLF、该行恰 4 个未转义 pipe，写回后校验无裸 LF）；memory.md 替换过时的
    「git 当前状态（2026-06-01）」块为本 spec 摘要（净行数 0，199 行，保 BOM + CRLF）
  - 回归归因（干净 HEAD 工作树 `D:\GT_plan_attr_wt` 同命令对照）：后端四表 / 试算表 / 取数契约组 **79 failed 与 HEAD 逐条相同**（0 新增）；
    前端 workpaper / formula 组仅本工作树红 17 条 —— 1 条是本 spec 引起（`e1AdjudicationPrefill.spec.ts` 的源码守卫仍找
    `flushSave` 里的 `startsWith('E1-adj-')`，任务 13 已把谓词抽到 `e1BackendOwnedKeys`）⇒ 守卫改为钉「flushSave 经由谓词 +
    谓词仍是 E1-adj- 前缀口径 + 行为断言」，变异 2/2 红；其余 16 条（C22 / A91 / B22B / D3）属并行工作的未提交改动：把本 spec 触达的
    3 个共享文件（`types/sse.ts` / `apiPaths/formula.ts` / `apiPaths/index.ts`）拷入干净 HEAD 后这些用例 63/63 全绿 ⇒ 与本 spec 无关
  - 一次性探针全部删除（`backend/tests/_*.py` 本 spec 所建者、`%TEMP%` 输出、备份目录、归因工作树）
  - 2026-09-30 追记（T17 实测后复核）：
    - INDEX.md 本 spec 行**已丢失**（并发提交重写过该文件，HEAD 与工作区均无此行）⇒ 重新登记于「一、Active Specs」首行，校验同上
    - 后端推送套件 + 阶段一回归 **299 passed**；前端 33 个相关 spec 文件 **387 passed**（此前记的预存红
      `j2NoteSubtableContract` P1 soe 已由并发提交 `68d73bd26` 撤销模板陈旧覆盖后转绿，非本 spec 所修）
    - 本轮改动文件 ESLint 0 error（45 条 warning 全不在本轮改动的 hunk 内）；vue-tsc 单区域：纯 TS 区域 0 错；含 `.vue` 的区域
      36 条报错均不在本轮改动的行上（其中本轮触达文件只有 J2 两页 4 条 TS7031，位于未改动的 `row-class-name` 模板代码；
      其余 32 条在经 import 传递进来、本轮未改的文件里）
    - 行数门禁抓出**白名单畸形条目**：`E1TabDisclosure.vue` / `g7SoeDisclosureModel.ts` 自 2026-08-16 登记起只有路径没有数字，
      `load_whitelist` 按「非两段即跳过」静默丢弃 ⇒ 登记从未生效。补基线（2012 / 1670，均为现算真实行数）+ 守卫
      `test_check_file_size_gate_cannot_be_bypassed.py` 层 3（真文件变异：改回只写路径 ⇒ 守卫红、门禁 exit 1；复原后逐字节一致、门禁 exit 0）
    - 保留 `backend/scripts/analyze/_incident_after.json`（五、49 事故写后快照），复原决定后删除
