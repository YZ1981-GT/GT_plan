# 平台全局显示设置收口：实施任务

> 状态口径：2026-10-29 按 brief 重排为「阶段 A 显示偏好与屏幕显示 → 阶段 B 账套导入单位归一 → 阶段 C 正式导出单位策略 → 终验」（design §14），共 29 个顶层交付单元。编号保留原任务号：拆分任务带阶段后缀（1A/1B/1C、6A/6C、11A/11B/11C、12A/12B/12C、13A-1、13A，终验仍为 13；13A-1 由 design §17 G7 从 13A 拆出，design §18 H2 把它排为阶段 A 第一个任务），各阶段末的运行时冒烟/验证与备份 commit 记为 `A-V`/`A-BK` 等。只有任务 0（设计期调查）已完成；其余均未实施，不得因既有单测通过提前勾选。历史归档只追加勘误，不回填。
> 分段门禁：一个阶段的全部任务及其 `-V`、`-BK` 完成后才进入下一阶段。迁移分组见 design §2，顺序与跨阶段依赖见 design §9，AC 归属见 requirements「AC 与交付阶段对应」。本清单没有 `*` 可选任务。

## 设计期

- [x] 0. 现状调查、评审修订与风险冻结（R1~R10）
  - 已先读 baseline/ownership；检测到既有 `spec-review.json=CHANGES_REQUESTED` 后又读完整 reviewDoc，未改写评审文件。按 17 项 finding 修订需求、设计、任务和 ownership，并在 design §10 逐项响应。
  - 恢复轮检测到 `spec-review-recovery.json=CHANGES_REQUESTED` 后读取其 reviewDoc，只修订该轮 4 项 HIGH、2 项 MEDIUM：兼容导入入口、旧 incremental apply、Word policy 版本证据、R 无损回滚、ratio_scale 与 PDF 密码；design §11 逐项响应。未重跑基线、未修改门文件或产品代码。
  - 当前恢复复审再次为 `CHANGES_REQUESTED`，已读取同门文件所指最新 reviewDoc，只修订本轮 5 项 HIGH、5 项 MEDIUM：账套入口闭集、staged 恢复协议、OnlyOffice policy 继承、组合/归档消费者、custom workbook authority、fixed pageKey CAS、审计日志脱敏、合同舍入校验、扫描范围闭合和独占 Playwright。design §12 逐项响应；NIT 按门契约未顺手处理。未重跑基线、未改门文件/INDEX/产品代码。
  - 当前门第二次迭代仍为 `CHANGES_REQUESTED`，已读取 reviewDoc，只修订其 4 项 HIGH、6 项 MEDIUM：四表/AccountChart staged 可见性、增量 UUID+合同 digest CAS、custom 两阶段可达链、全文件出口分类、客户端 mutation epoch、Decimal 空值/finite 合同、PDF 422 脱敏、候选 Git tree 身份、legacy 元数据精确恢复和共享 PG READ ONLY。design §13 逐项响应；NIT 未处理。未重跑基线、未改门文件/INDEX/产品代码。
  - 已真实读取偏好/layout/路由、字体 CSS、公共表格、project store/config、导入 detect→submit→两 worker→write、附注 kind/clone、Trial/Report/Note/WP/bulk/PDF 导出与 CI；确认 `/settings` admin-only、Dashboard 无金额、PDF DTO/鉴权/空数据、增量先删后建 job 等评审事实。
  - 本轮复跑显示相关 Vitest **74/74 passed**，同时 grep 证明 `useGlobalTableLayout`/`exportUnit` 无生产调用、GtWpRenderer 未绑 style。旧格式脚本仍报 **1016**；探针现算 regex hits=1020、131 条 allowlist 仅 4 条有效；ESLint 现算 **2323 条/699 文件**。
  - 真实 PG 数字只沿用只读 baseline 快照并标为实施前重跑项；45 个 active dataset 暂冻结为 `legacy_unknown`。当前无可接受 computedStyle 证据，所有产品代码、真实迁移、Playwright 和正式导出验收仍未实施。（AC-12、AC-23、AC-26）
  - 阶段 A 设计门首轮（workflow `wf_daadceb7157e9d26`，门文件尚不存在）：按 HEAD `236cd334e` 复核阶段 A 涉及的代码，在 design §15 追加 A1~A10 并对应到任务：A1 迁移取号增加目标库 `schema_version`、落库前核对 pending 恰为本组 V（1A/1B/1C 与各 -V）；A2 候选验证模式（13A：环境变量未设置时不调用 git，`startup_registry` 首位身份任务，`CANDIDATE_MODE_POLICY` 跳过启动迁移、事件重放、恢复与全部 worker，Vite 关闭 dts 并约束端口与代理）；A3 独立查账窗口 `LedgerStandalonePage` 同样安装 runtime（5）；A4 displayPrefs 兼容合同、线值枚举与 strict 校验（4、5）；A5 数据集 `unit_state` DTO 与唯一分类函数（7，A/B/C 接口）；A6 附注表对不上目录时的 `measure_status` 与原值显示（6A）；A7 GtWpRenderer 解构后绑定 fontStyle、删除 GtAmountCell 的 `unit` prop（5、6A、7）；A8 扫描范围改为 include/exclude 常量加顶层目录 scope（11A）；A9 `amountColumnSemantics`/`isAmountColumn` 只用于输入控件选型（6A、11A）；A10 零行 UPDATE 故障注入与 A-V 恢复口径（1A、A-V）。requirements 只改 AC-23 的逐 scope candidates 措辞（原文要求每个 scope 的 candidates 非零，`permissions`、`types` 等 scope 无法达成）。未改门文件、INDEX 和产品代码；ownership 台账追加本轮新增的边界路径。
  - 阶段 A 设计门第 2 轮（workflow `wf_daadceb7157e9d26`，门文件为 CHANGES_REQUESTED：HIGH 2、MEDIUM 9、NIT 9）：已读门文件与 reviewDoc，按 HEAD `6c17996ad` 复核，只处理 11 项阶段 A/跨阶段 HIGH/MEDIUM，design §16 F1~F11 逐项响应；与 F 项同一规则的 NIT 并入，其余 NIT 在 §16 末表记处置；阶段 B/C 的 6 项留在 backlog。F1 迁移先于 ORM（1A 五步、A-V 只核对 pending 为空）；F2 `run_uvicorn.py` 候选分支、身份任务移到 `setup_logging` 之后、`CANDIDATE_MODE_POLICY` 理由码闭集、新增三项 skip 与启动期 SQL/spy 判据（13A）；F3 端口只经 `UVICORN_*`/`VITE_DEV_PORT` 传入并在监听后核对（13A）；F4 AC-08 证据改为浏览器、A-V 拆为①②（5、A-V）；F5 只有顶层列可固定、TrialBalance 只有明细主表接固定列（5、6A）；F6 PATCH 区分显式 null 与未提交（2、4）；F7 PG 用例在临时 schema 内执行、审计日志换测试库（1A、2、3）；F8 附注列级 matched 规则与 `table_id`（6A）；F9 计数单位、候选 worktree 计数与 >88 时请示（11A）；F10 el-table-v2 字号选择器、`useTableDensityMetrics` 与重新挂载（5、6A、13）；F11 项目单位对其他用户在下次加载项目上下文时生效（3、A-V）。同步改写了与 §16 矛盾的子项：1A 第 2、3 条，2 第 1~3 条，3 第 2、3 条，4 第 3 条，5 第 2~4 条，6A 第 1、2 条，11A 第 2 条，13A 第 2、3 条，A-V 第 2 条，13 第 3 条；任务标题与勾选状态不变。requirements 未改；未改门文件、INDEX、backlog 和产品代码；ownership 台账追加本轮新增边界。
  - 阶段 A 设计门第 3 轮（workflow `wf_ea78292dbbb03cbb`，门文件为 CHANGES_REQUESTED：HIGH 1、MEDIUM 8、NIT 15）：已读门文件与 reviewDoc，按 HEAD `219018c28` 复核，只处理 9 项 HIGH/MEDIUM，design §17 G1~G9 逐项响应；N1、N13、N14、N15 并入对应 G 项，其余 NIT 未处理；阶段 B/C 发现留在本工作流目录的 backlog。G1 render schema 映射表、核心清单（三份 `c-note-table`）与非核心 unknown 只减基线（6A、12A）；G2 合并附注 table_id 取模板条目 `id`（6A）；G3 固定列键带表或模式身份、`fixed_columns` 值改为 `{columns, saved_at}`、客户端按 `saved_at` 淘汰（2、4、5）；G4 逐 kind 显示规则，R6 与 AC-11 期望改为 `20.00%`（6A）；G5 未登记表按元口径格式化、只读探针现算附注 matched 分布、终验样本表须 matched（6A、12A、13）；G6 分析器数值候选判定常量与四条核心违规谓词（11A）；G7 拆出 13A-1 排在 11A 之前（13A-1、11A、13A、各 -V）；G8 A-V 前提清单与恢复口径（A-V）；G9 迁移草稿阶段同时起草 ORM 草稿（1A）。改写的子项：头部计数，1A 第 2、3 条，2 第 1 条，4 第 1、3 条，5 第 3 条，6A 第 1~4 条，新增 13A-1，11A 第 2 条，12A 第 1、3 条，13A 第 1 条，A-V 新增第 2 条（前提清单）并改原第 2 条（现第 3 条）的启动说明，阶段 B、C 依赖说明，B-V、C-V 启动说明，13 第 2、3 条；requirements 只改 R6 与 AC-11 的比例期望值。未改门文件、INDEX、backlog 和产品代码；ownership 台账追加本轮新增边界。
  - 阶段 A 设计门第 4 轮（workflow `wf_ea78292dbbb03cbb`，门文件为 CHANGES_REQUESTED：HIGH 1、MEDIUM 2、NIT 16）：已读门文件与 reviewDoc，按 HEAD `626bcef99` 复核，只处理 3 项 HIGH/MEDIUM，design §18 H1~H3 逐项响应；R4-N2 并入 H1，其余 NIT 未处理。H1 render-config 逐 sheet 判定抽为纯函数、render schema 核心清单按离线算出的 reached_by 收录（预计初始为空）、HTML 底稿核心面改为 `d1/D1TabDisclosure.vue`、GtCNoteTable 单位字段改标签并显示屏幕单位（6A、11A、12A、A-V、13）；H2 13A-1 移为阶段 A 第一个任务，1A 与 6A 的候选树各自现建现删（13A-1、1A、6A）；H3 drift 两侧都在临时 schema 里经 PG 渲染后比较（1A）。改写的子项：头部说明，13A-1 移到 1A 之前并改标题说明，1A 第 2、3 条，6A 第 1~4 条，11A 第 1 条，12A 第 1 条，A-V 第 2 条，13 第 3 条；任务标题与勾选状态不变。requirements 未改；未改门文件、INDEX、backlog 和产品代码；ownership 台账追加本轮新增边界。

## 阶段 A：显示偏好与屏幕显示

> 不依赖阶段 B/C。

- [ ] 13A-1. 候选提交与锁定 worktree 工具（R10；design §17 G7、§18 H2：阶段 A 第一个任务，只依赖 git；1A、6A、11A、13A、各阶段 -V/-BK 与终验复用）
  - 实现 `scripts/check/candidate_tree_identity.py` 的 `build`（按清单文件逐项取工作树整文件或 tmp 下预先合好的本任务块内容，在私有 index 上 `read-tree HEAD`/`update-index`/`write-tree`/`commit-tree`，私有 index 路径只经子进程 env 传入，不移动任何 ref）、`checkout`（分离头 worktree 建到 `tmp_global_display_settings/<名称>` 并 `git worktree lock`，建好后 `git status --porcelain` 必须为空）与 `release`（先 `cmd /c rmdir` 拆自建 node_modules 联接，再 unlock、删目录、prune）。
  - 测试：`build` 前后 `git for-each-ref` 逐行相同、父进程 `os.environ` 不含 `GIT_INDEX_FILE`、所用 index 不是 `.git/index`、worktree 已锁定、`release` 后联接目标目录仍在；把私有 index 换成默认 index 的变异必须红并逐字节还原。（AC-24 的 A 部分）

- [ ] 1A. 阶段 A 基线复算与 A 组迁移（R2、R4）
  - 现扫工作树、`git ls-tree origin/spec/disclosure-note-doc-upload-and-batch-fill backend/migrations` 与 gt-plan `migration_status` 三处并集最高迁移号，A 组取其 +1（design §2）。通过数据库级只读入口（任务 9 inspector 落地前为 tmp 下同纪律只读探针，design §14）重新现算 PG 项目/schema 状态并重跑格式守卫/ESLint 基线；第一条业务 SQL 必须是 `SET TRANSACTION READ ONLY`，全程单连接、finally rollback，输出放 `tmp_global_display_settings/`。更新 ownership，不引用本轮旧快照当完成证据；隔离 PG 故障注入 UPDATE 必须得到 SQLSTATE 25006。
  - 按 design §16 F1 五步执行，第①③④步按 design §17 G9 修订：先在工作流目录同时起草 A 组 V/R（新增 typed `user_display_preferences` 与 `projects.amount_unit`，DDL 幂等，不读写四表金额）与不被 `app` 导入的 ORM 草稿 `orm_draft_display_prefs.py`，用临时 schema 夹具跑通 V/R、CHECK、R_A 与「V_A 对草稿」的 drift（比较方法按 design §18 H3：在同一临时 schema 由元数据建探针表，两侧经 `format_type`/`attnotnull`/`pg_get_expr`/`pg_get_constraintdef` 逐项比较并先断言列集合非空；`GT_DISPLAY_PREFS_ORM_SOURCE` 指向草稿；改草稿默认值、去掉 CHECK 枚举 `wan`、改 `String` 长度三项变异各自必须红）；再复制进 `backend/migrations/`，经只含本组文件的迁移目录 `run_pending()` 落共享库，断言 executed/failed 并核对 `schema_version` 的 filename/checksum（目标号已按相同 filename/checksum 登记时跳过 `run_pending` 并记录，不一致才请示）；落库成功后才按草稿登记 ORM（含 `server_default`）、response schema 与 router，并对真实 ORM 重跑同一 drift 用例、比较草稿与真实 ORM 逐项相同，输出存工作流目录。
  - R_A 在任何 DROP 前以 `RAISE EXCEPTION` 检查非默认项目单位与任一偏好行并整单回滚。补 PG/SQLite CHECK（SQLite 用例依赖 ORM，排在 ORM 落地之后）、重复迁移号、schema drift 与两类回滚保护测试，PG 用例按 design §16 F7 在临时 schema 内执行；用 13A-1 现建含 1A 改动的候选 worktree 证明 schema 变更不改账套金额，用完 `release`（design §18 H2）。（AC-01、AC-05、AC-21 的 A 组部分）

- [ ] 2. 当前账号偏好 API、默认合同与并发隔离（R2、NFR 安全）
  - 新建 schema/service/router 并注册 `GET/PATCH /api/users/me/display-preferences`；实现完整默认 JSON、严格 extra/range/fixed_columns 限制、字段级 patch（显式 null 与未提交按 design §16 F6 区分）、revision CAS，service 只 flush、router commit/rollback。`fixed_columns` 按 design §17 G3③：请求值为 `{columns}`、响应值为 `{columns, saved_at}`，service 对未改变的键保留 `saved_at`，请求带 `saved_at` 为 422，64KiB 按存储后的规范 JSON 计算。
  - 无记录首写用 SAVEPOINT；并发唯一键竞争回读 current 并返回 409。在实际注册的 `middleware/audit_log.py` 为本 PATCH 增加精确 route redactor，router 只通过 request.state 交 revision/顶层 changed_fields，固定列只记字段名不记 pageKey。TestClient 覆盖 401、A/B 隔离、默认、部分/空 patch、全部边界、首写竞争、旧 revision、DB 故障，并在真实 middleware stack 后查询 logs 证明完整偏好未落库（审计日志会话按 design §16 F7 换成测试库）。
  - 逐项去鉴权、把 WHERE user_id 改成请求值、去 revision、把冲突当成功、移除 redactor 或把 `exclude_unset` 换成 `exclude_none` 做变异，须红在对应安全/并发/日志/跟随项目断言。（AC-01~AC-03、AC-24）

- [ ] 3. 项目正式单位五层一致、project store 时序与设置入口（R4）
  - 新建 project_config_service，config GET=readonly、PUT=`project:edit`，严格 yuan/qian/wan，去 `getattr/hasattr`；Project 详情 schema/mapper和前端类型携带 amount_unit。
  - project store 新增 nullable projectAmountUnit：换项目同步清空、contextSeq/ID 双检查晚到响应、缺失/非法/失败降级规则；ProjectSettingsCenter 增加“项目默认金额单位”（说明文字与其他成员的生效时点按 design §16 F11），成功响应只更新同一当前项目。
  - 端点/Pinia 测三值、422/403/423/404、A(wan)→B(慢/失败)→A、无项目、显式 qian override、另一账号在下次 `loadProjectContext` 后才取到新单位；逐层删 ORM/mapper/service/router/store 清空的变异均红。（AC-05、AC-06、AC-24）

- [ ] 4. 前端账号加载、30 天 userId 缓存与 effective store（R2、R3）
  - 重写 displayPrefs 并增加 API/normalizer/Decimal formatter/runtime：nullable override、项目 fallback、完整 server state、300ms 增量 PATCH；每个 scalar 和 fixed page upsert/delete 都以单调 mutation epoch记录。发送时冻结值+epoch+owner generation，响应只清同 epoch；在途新编辑进入下一代。409 只对原代际以 server current为基底重放未变化操作并最多重试一次。键数将超过 100 时按 design §17 G3④ 以 `saved_at` 淘汰未挂载的最旧键（delete 墓碑走同一 epoch），可淘汰键不够则本次不保存并提示。
  - 仅用 `gt_display_prefs:v3:${userId}`；旧 key 删除不迁移。账号切换取消 timer/request、清 pending/脏页/tombstone/内存并按 userId+sequence 丢晚到结果；过期 30 天整份缓存与 pending 不应用；捕获 Storage 安全/配额异常。
  - Vitest 覆盖默认线值、优先级、`followProjectUnit()` 的 PATCH 体显式含 `amount_unit_override: null`（design §16 F6）、重建 store、A→B→A、乱序、TTL、离线、损坏 JSON、decimals=999、两设备同 revision修改不同/相同 pageKey、删除、第二次冲突、超 100 键淘汰最旧未挂载键与可淘汰键不够时不保存；再挂起首个 PATCH，分别二次改同一 scalar、同页覆盖/删除、异页修改及切账号，断言新 epoch不被旧成功/409清除并进入下一 flush。去 userId/TTL/generation/normalizer/epoch比较/pageKey合并/tombstone/范围保护变异必须红。（AC-04、AC-06、AC-09、AC-10、AC-24）

- [ ] 5. 独立显示设置路由、根 CSS、字体与固定列公共层（R1、R3、R5）
  - 新建 DisplaySettingsView/DisplayPreferencesPanel；保留 `/settings` admin 门，增加认证 `/display-settings`，Aa compact 面板与管理员 Tab 复用。普通用户设置入口只到新页；不挂载/修改 UserSettingsExtension 或两个超范围 localStorage key。
  - DefaultLayout 接 runtime/useGlobalTableLayout；更新 gt-tokens/global/gt-table/**gt-polish**：固定 GT→系统回退、不加字体资产，`--el-font-size-base` 与真实表头/正文/输入/Teleport/wp 及 `.el-table-v2__header-cell/__row-cell` 选择器读动态字号/密度，移除固定 12px 覆盖。
  - 新增 usePreferredFixedColumns 和 GtTableDisplaySettings（props/emits 按 design §4.3）；GtEditableTable 与原生表按 design §17 G3① 的带表或模式身份的持久化键实现 `mandatory ∪ saved∩allowed`、仅左固定和同键内的 stale 提示，`save` 只替换当前键，无键或键超 100 字符时设置入口禁用并提示；只有顶层列可固定，分组列不开放（design §16 F5）。测试含表 X 固定后切到表 Y 无 stale、回到 X 仍生效，normal 与 compare 互不影响。新增 `useTableDensityMetrics` 供核心 v2 表绑定行高，并在字号/密度变化后重新挂载（design §16 F10）。
  - 路由、四档根变量、jsdom CSSOM 选择器合同、真实 Element Plus DOM 类名（含 `el-table-fixed-column--left`）、三密度/doLayout/fixed 交集与 LedgerPenetration v2 分支测试；四档 computedStyle 由 A-V① 浏览器核对（design §16 F4）。普通 auditor 可进新页但不可进管理页。恢复 gt-polish 12px、删布局调用、删任一 pageKey 接线的变异必须红。（AC-07、AC-08 的 vitest 部分、AC-09、AC-24）

- [ ] 6A. 跨层 measure kind、公共 formatter 与核心屏幕收敛（R5、R6；NoteWord 普通/clone 导出路径见 6C）
  - 建七类后端/前端枚举、`RatioScale=fraction|percent_points` 与条件校验合同并对拍；GtAmountCell/displayAmount 只处理 amount，GtMeasureCell 按 design §17 G4 逐 kind 显示规则输出（0.2 fraction 与 20 percent_points 都为 `20.00%`，两种 divisor=1），未登记分支按元口径格式化。GtColumn 归一默认 text但核心 numeric 必须显式，ratio 必传 ratioScale且其他 kind 禁传；render schema 由 `wp_render_schema_service` 按 design §17 G1① 映射表换算 measure_kind/ratio_scale 并随 render-config 下发，非核心表含 unknown 时整表走未登记分支、不拒绝渲染；核心清单按 design §18 H1：先把 render-config 逐 sheet 判定原样抽到 `backend/app/routers/wp_render_config_sheet_classify.py`（表驱动用例 + AST 守卫，16 个 render-config 测试文件的失败集合与同一 HEAD 相同），再由只读 `render_schema_measure_audit.py` 离线算各 schema 的 reached_by；`render_schema_core.json` 只收 reached_by 非空的项，`--check` 重算 reached_by（预计三份 `c-note-table` 都为空、初始 `entries: []`、三份 YAML 不改），运行时核心 unknown 按 §18 H1③ 返回 `measure_contract_error`；非核心 unknown 基线只减不增；`ValueType.rate/integer` 与原币列不做机械映射，按 design §16 末表显式声明。
  - 为单体表注入稳定 table_id；合并附注 table_id 取项目合并模板版本中按 `section_id` 查到的模板条目 `id`，禁用 `ConsolNoteData.id`（design §17 G2，生成器校验两版 `section_id → id` 一一对应且两版不重复）。由标题行库+逐表 override生成四版 note_table_measure_catalog，ratio scale 不得从标题猜。单体详情 API 与 `GET /api/consol-note-sections/{standard}/{section_id}` 下发等长 column_ids/kinds/ratio_scales、表级 `table_id` 与 `measure_status`（单体按 design §16 F8 列级判定，原表头按 §17 G2 深拷贝整张表；合并按 §17 G2），由 Disclosure/ConsolNote 屏幕消费；同一 catalog 与 ID 供 6C 的 NoteWord 两条路径和任务 10 的 sidecar 复用。按 design §17 G5② 用只读探针（在 13A-1 现建的含 6A 改动的候选 worktree 上以子进程运行，design §18 H2）现算共享库附注 matched/unmatched/invalid 分布，输出写入工作流目录与 12A 文档。
  - 按 design §4.4 与 §16 F5、§17 G3（TrialBalance 固定列只接明细主表，各页持久化键带表或模式身份）修改 TrialBalance、ReportView/权益/减值、Disclosure、GtWpRenderer/HTML 底稿（核心面为 `d1/D1TabDisclosure.vue`：金额格改 GtAmountCell、比例格改 GtMeasureCell fraction、不提供用户固定列，design §18 H1④；GtCNoteTable 只做 kind 消费、未登记提示与 §18 H1⑤ 的单位标签；GtWpRenderer 显示 `measure_contract_error`）、合并/worksheet、Ledger；Dashboard 只接字号/密度并反证项目数/年度/工时/进度不缩放。移除核心固定字号和裸金额旁路。
  - 逐页测试 10000 金额及 quantity/count/exchange_rate/unit_price/text（按 design §17 G4 各行夹具，含零值、负数、6 位以上小数），并用 0.2 fraction 与 20 percent_points 双夹具测屏幕；G1 映射表每行、非核心整表未登记、核心 unknown 报错（夹具核心清单）、路由纯函数与 reached_by（design §18 H1⑦）、D1TabDisclosure 的万元/元/比例与 `data-gt-value`、GtCNoteTable 单位标签，以及合并附注 `data` 无 `id` 判 matched 各一个夹具；四版目录与 render schema 审计 `--check`。绕 formatter、改 kind、删除/互换 ratio_scale、删 runtime.fontStyle、把合并 table_id 取成数据行主键、把 unknown 改成 amount、count 读账号小数位、把 D1TabDisclosure 任一 GtAmountCell 换回 fmtAmount 字符串、删除 `elif pkg_sheets and ovr` 分支的逐点变异均红。（AC-08、AC-10、AC-11 的屏幕部分、AC-12、AC-24；稳定 ID 供 AC-19）

- [ ] 7. 附注第二单位删除与数据集单位三态 presenter（R7）
  - 删除 DisclosureEditor 的 `gt_note_amount_unit`、noteUnit/select 和所有 `:unit` override；屏幕只读 effective store，正式导出代码不得 import 该 store。
  - 后端把 source_summary 归一为 normalized_v1/legacy_declared/legacy_unknown，前端唯一 datasetUnitPresentation 供 LedgerPenetration 与 TrialBalance 使用；只有 normalized 显示存储元/因子，历史声明与 unknown 按 design 文案显示。阶段 A 后端分类器只产出两类 legacy（存在 `unit_normalization` 也 fail closed 为 legacy_unknown），normalized_v1 分支用前端 DTO 夹具验证，由任务 8 接入严格合同解析后才产出（design §14）。
  - 删除 Ledger load 时 `displayUnit='yuan'`，补跟随项目/千元选项；数据集/页面/账号切换夹具验证元数据状态与显示单位独立。GtInfoBar 若改“项目单位”，AST+组件测试逐调用方证明不是金额单位。（AC-13 的 A 部分、AC-24）

- [ ] 11A. 唯一 fail-closed AST 守卫（前端屏幕金额）、可信 ledger、历史勘误与 CI 单一步骤（R6、R10）
  - 用共享 Vue/TS AST analyzer重写 ESLint rule与格式CLI；固定production scope从Git候选算eligible，逐scope闭合parsed/skipped。维护核心symbol manifest（本任务登记屏幕核心符号，含 design §18 H1④ 的 `d1/D1TabDisclosure.vue`，正式导出触发函数由 11C 补入）；CLI JSON 键按 design §14 分阶段递增，本任务固定前端键。
  - 退役 131 条行号 allowlist和 92/88 双指标/CI `|| true`，CI 只保留唯一格式 CLI 一个步骤；建立有 JSON Schema 的 parser exemption 与 legacy ledger，有限 verify 谓词逐项校验 fingerprint、理由和已修即删。计数单位按 design §16 F9，数值候选判定按 design §17 G6 的 `NUMERIC_CANDIDATE_RULES` 常量（显式 kind 来源、S1~S4 结构信号、`LEGACY_NUMERIC_FORMATTERS` 闭合、关键字只升级不单独定罪），核心违规谓词另含 G6⑤ 的 b~d（金额 formatter 作用于非 amount、`<GtAmountCell :unit>`、核心 v2 renderer 固定 px 字号），每个信号与谓词各配正反 fixture，删除任一信号的变异须红；第一步在 13A-1 建立的候选 worktree 上出逐 scope、核心/非核心计数并记入工作流目录。唯一 baseline 只在 `git status --porcelain` 为空的候选 worktree 用 `--update-baseline` 生成、拒绝上调且必须≤88，生成的基线文件逐字节复制回主工作树，之后的候选树须 `--check` 通过；修完核心与公共路径仍 >88 时 send_message warning 请示，不自行扩大范围、改计数单位或增加 exempt，不抬线。
  - 每个谓词做正反/parser crash/空扫描 fixture；把 include root 收窄、排除核心文件、parser 静默 skip 均须红 `SCAN_SCOPE_DRIFT`，新增生产文件自动进入 eligible。新 spec/INDEX 只追加本任务旧“全部迁移”勘误和动态真实数量/后续批次，不改历史归档。（AC-23 的 A 部分、AC-24、AC-26）

- [ ] 12A. 屏幕显示开发文档（R10）
  - 更新 `docs/frontend/display-preferences.md`：默认元、账号wire/30天缓存、per-item mutation epoch与fixed CAS、项目fallback、三层优先级、设置路由、字体/CSS、fixed矩阵（带表或模式身份的持久化键与 100 键淘汰）、七类measure+ratio_scale及逐 kind 显示规则、render schema 核心清单（含 reached_by 与离线算不到的两类路由，design §18 H1②）与非核心 unknown 现算数量、D1TabDisclosure 零值/负数显示的统一与保留的 12px 说明文字、附注 matched/unmatched/invalid 现算分布、数据集三态，以及个人偏好不进入正式导出的边界（导入、导出细节分别由 12B、12C 文档承接）。
  - 示例只能调用新 API/组件/composable，不再展示默认万元、直接 v-model effective 值、未分区 localStorage 或个人单位控制导出；明确 UserSettingsExtension 两项不在本 spec。
  - 文档守卫核对屏幕 API/枚举/key、核心页面矩阵、ledger 动态数量、render schema unknown 基线数量与代码，后续批次如实列出。（AC-26 的 A 部分）

- [ ] 13A. 候选 tree 身份工具（R10；供各阶段冒烟与终验复用）
  - 复用 13A-1 的 `build`/`checkout` 生成 candidate commit/tree 与锁定的分离头 worktree（design §17 G7），启动前要求无受跟踪改动；本任务只做启动身份与端口部分。
  - 后端启动钩子与 `vite.config.ts` 各自从 cwd 解析 `HEAD^{tree}`，与 `GT_EXPECTED_CANDIDATE_TREE_OID` 不等、解析失败或 worktree 不干净即拒启动；候选模式的预引导迁移跳过、身份任务位置、`CANDIDATE_MODE_POLICY` 理由码闭集与端口通道按 design §16 F2/F3，启动器只经 `UVICORN_PORT/UVICORN_HOST/VITE_DEV_PORT` 传端口并设 `GT_BOOTSTRAP_DONE=1`；启动日志、`backend/app/api/health.py` 的 header/body 与 `src/main.ts` 写入的前端 marker 同时暴露 expected/actual。
  - 从错误 worktree 启动、仅回显注入值、worktree 有受跟踪改动三种变异，以及删 `run_uvicorn.py` 候选分支、把任一 skip 任务改 run、端口经 `--port`/`UVICORN_PORT=9980`/`UVICORN_RELOAD` 或 Vite `--port 3030` 传入，均须红在预期断言；全量回归与最终提交绑定留终验 13。（AC-24、AC-25 的身份部分）

- [ ] A-V. 阶段 A 运行时冒烟/验证
  - 跑阶段 A 相关后端 pytest（`-p no:playwright`）、前端 vitest、11A 唯一格式 CLI/ESLint 与 vue-tsc（候选树相对同一 HEAD 无新增，注入 TS2322 证明真跑）；红测试先在同一 HEAD 复跑归因，本阶段各任务列出的逐点变异全部红在预期断言并逐字节还原。
  - 开始前按 design §17 G8 的前提清单用只读探针核对账号 A/B 的权限与成员关系、【测试】standalone 项目 P 的数据，任一不满足即 send_message warning 请示，请示内容固定列出各项现状，不自行补齐；成员关系只在用户同意后由文档登记的 admin 经平台项目成员接口建立并在 finally 移除。A-V 只在 P 上冒烟 TrialBalance、ReportView、DisclosureEditor、D1 底稿「附注上市」页签（`D1TabDisclosure`，design §18 H1⑥）与 LedgerPenetration，合并页留终验。开始前记录 A、B 偏好与 P 的 `amount_unit`，finally 经 PATCH 与 config PUT 恢复并回读核对，新建的偏好行保留并在证据中注明会阻断共享库 R_A。
  - 用 13A-1 与 13A 从阶段 A 候选树启动独占非 3030/9980 端口；A 组 DDL 已在 1A 落库，启动前只用只读探针核对候选树 pending 为空，非空即 warning 请示（design §16 F1）。按 design §16 F4 分两部分，均用名称含【测试】的项目：A-V① 一个已批准测试账号（不用 admin 或他人账号）冒烟四档 computedStyle（11/12/13/14px，含表格 body/header/表内输入/Teleport/HTML 底稿格与一处非表格默认尺寸组件）、元→万元、页面切换、刷新/重登、固定列（含分组列不可固定）/密度，以及修改者立即看到项目单位变更；A-V② 第二个已批准账号验不继承 A 的偏好、刷新后看到新项目单位（design §16 F11）。el-table-v2 的浏览器核对留终验。写入只限这两个账号的偏好和该【测试】项目，finally 恢复并核对业务字段。账号不可用时 send_message warning 暂停请示，不以其他方式替代；冒烟证据不替代 AC-25。用后 unlock、`cmd /c rmdir` 拆自建 node_modules 联接、删目录、prune。

- [ ] A-BK. 阶段 A 备份 commit 对象
  - 以当时 HEAD 为基，私有 index（只经子进程 env）只加入 ownership 登记的本任务路径与改动块（共享文件只含本任务块），write-tree/commit-tree 生成不移动任何 ref 的备份 commit；commit OID、tree OID、基底 HEAD 与路径清单写入 `tmp_global_display_settings/` 下当前工作流目录，并以 `git cat-file -t` 核验。完成后向父会话发一条阶段 A 中文进度消息。

## 阶段 B：账套导入单位归一

> 依赖阶段 A 的任务 7（分类器/presenter）、11A（守卫 CLI）、13A-1 与 13A（候选 worktree 与 tree 身份工具）。

- [ ] 1B. 阶段 B 基线复算与 B 组迁移（R8）
  - 按 1A 同一三处现扫重新取号，B 组号必须大于 A 组已用号；经同一数据库级只读入口现算 PG 数据集状态（任务 9 inspector 落地后以其输出为准）并更新 ownership；baseline 中 45 个 active 数据集冻结为 `legacy_unknown` 只作快照。
  - 动态创建 B 组 V/R 配对并登记 ORM：新增 `ledger_import_attempts`（base token 仅 dataset UUID+unit contract digest，不新增 dataset version）。DDL 幂等，不更新四表金额。
  - R_B 在任何 DROP 前对任一 attempt 行 `RAISE EXCEPTION` 并整单回滚；补 PG/SQLite CHECK 与唯一约束、重复迁移号、schema drift 和回滚保护测试；候选树证明本组 schema 变更不改账套金额。（AC-15、AC-16 的 attempt 存储前提，AC-21 的 B 组部分）

- [ ] 8. 服务端单位证据、账套入口闭集、staged 恢复与两引擎只换算一次（R8）
  - 实现 UnitDetectionSummary/UnitConfirmationInput/UnitNormalizationContract：bundle 流式写 SHA-256；三条正式 detect/preview 返回同一 unit_detection。合同 validator 固定 yuan/qian/wan 因子 1/1000/10000，校验 detection/confirmation/job.created_by/canonical digest；runner 每次 claim/retry/resume 重验。所有已注册 preview/detect 改项目 edit 门。`dataset_unit_contract` 的 normalized_v1 分支接入 `unit_normalization.py` 的严格合同解析、按增量基准门同一口径重算 canonical digest（任务 7 在阶段 A 只产出两类 legacy），并补真实导入数据集在 LedgerPenetration/TrialBalance 显示存储元与因子的核对。
  - 将已注册但无生产前端调用的 `/account-chart/import`、`/api/projects/{project_id}/import` 固定退役为 410 `LEDGER_IMPORT_MOVED_TO_CONFIRMED_JOB`，不再 import/call 旧 service/writer；既有 E2E 改验 410。建立从真实 `app.routes` 与 ImportJob/五表 writer/activate/resume 反查的 `LEDGER_IMPORT_ENTRYPOINTS`；status 按对象反查项目 readonly，recovery 校对象归属+edit且不收新金额，双向守卫拒绝任何未登记合同旁路或自由豁免。
  - `account-chart/import-async` 与 `ledger/smart-import` 连同 v2 submit 共用确认合同：直接文件无 token+digest 时仅落 bundle并 428，queue/job/四表 0 写；`incremental/detect` 返回 active `base_dataset_id/base_unit_contract_digest` 与服务端 periods，LedgerDataManager→LedgerPenetration原样提交，三个 submit 都在建 job 前过 shared helper/active preflight并持久化 unit_confirmation、完整 contract/digest、payload_style与 plan。退役 `/ledger-data/incremental/apply` 为固定 410。
  - 增加 `ledger_import_attempts` 与 stage-only writer：四张 Tb staged 行统一 `is_deleted=false`；重写 `dataset_query` 为 exact active / no-active-only-NULL-legacy / failure-raises，迁移 `LEDGER_TABLE_READ_SURFACES` 反查出的全部生产读者并禁裸 `project/year/is_deleted`。AccountChart staged client 行固定 `is_deleted=true`，独立 predicate；短激活按“隐藏旧或legacy→放开新”满足 partial unique，rollback逆操作。pipeline/smart批次可commit但只写stage；每批从全部登记 reader 验证旧 effective 结果不变。最终 merge、科目可见性、active状态、ActivationRecord、outbox和attempt在项目年度锁下短事务完成，失败按dataset_id清空五表。
  - 恢复只认 attempt 证据：submit、seal、activation三次在锁内要求当前 active UUID+unit contract digest等于 detect token；sealed且合同/bundle/row counts/post-hash/base token全一致才 activation-only，不再 converter/normalizer；其他 retry先清旧stage再建新attempt。`current_phase`仅显示。两引擎无默认必传 attempt/stage/contract/plan；convert后首次write前共用 `_AMOUNT_FIELDS_BY_TABLE`。金额 converter只产 `Decimal|None`，None稳定hash；非法非空值/NaN/±Infinity fail closed，qty与全部 *_fc不换。
  - 唯一金额内核对 None原样保留，对 finite Decimal执行 `value*factor`、`ROUND_HALF_UP`到0.01并检查Numeric边界；非空不可解析报 `LEDGER_AMOUNT_INVALID`，NaN/±Infinity报 `LEDGER_AMOUNT_NOT_FINITE`，错误只含file/sheet/row/field。单元+TestClient+PG覆盖全部 preview/retired/submit/recovery、edit门、direct-file 428、旧apply 410、base token三次漂移、合同篡改、missing/conflict/unsupported、legacy active零写、两引擎逐批可见性、首次无active/legacy NULL、active查询失败、AccountChart激活/rollback/partial unique、清理/activation-only/短事务、三因子、None/null token、非法/非有限值、正负半分、边界溢出和重复归一；逐点变异必须红。（AC-13 的 B 部分、AC-14~AC-17、AC-23、AC-24）

- [ ] 9. 既有数据只读检查、未来 apply/rollback 双闸门与可逆证据（R8）
  - 新建与 writer 物理分离的 shared-PG inspector：单一 connection 的第一条业务 SQL 为 `SET TRANSACTION READ ONLY`，断言 transaction_read_only=on，所有 helper 禁另开连接，finally rollback；按 normalized/legacy declared/legacy unknown 输出动态数据集数、四表逐字段 row count/sum/max/溢出风险与 canonical hashes，不按金额大小猜单位，输出只放 tmp。
  - 未来写脚本使用显式 apply/rollback 子命令；apply 必须环境变量+`--apply`+dataset双录+source unit，rollback还须最后未回滚 normalization version。apply history保存 presence-aware单位元数据 canonical snapshot+digest；rollback闭合当前 after-hash→反向 before-hash后精确恢复原 legacy_declared/legacy_unknown状态，再追加独立 history。四表、unit metadata、history和hash在单数据集事务内，保留source_summary其他键。
  - 隔离 PG 自动测试逐个缺闸门、None/finite/hash、非最后版本、快照篡改、恢复后增量门重新拒绝及任一表失败整单回滚；read-only入口故障注入 UPDATE精确报SQLSTATE 25006并对拍row count、金额hash与source_summary hash。本任务在共享PG只运行inspector，绝不运行真实apply/rollback，未来仍需用户另行放行。（AC-18、AC-26）

- [ ] 11B. 账套读取面与入口闭集接入唯一守卫（R8、R10）
  - 把任务 8 建立的 `LEDGER_TABLE_READ_SURFACES`（四表/客户科目读取与 active predicate）与 `LEDGER_IMPORT_ENTRYPOINTS`（真实 `app.routes` 与 ImportJob/五表 writer/activate/resume）接入 11A 的唯一守卫：AST 与登记双向相等，任一裸读、未登记入口、失效 helper 或自由豁免均以 `SCAN_SCOPE_DRIFT` 或对应机器码失败；结果摘要并入 CLI JSON，`ledger_read_surface_results` 自本阶段起为必含键，CI 仍为同一命令。
  - 正反 fixture 与磁盘变异：删一个 reader 的 active predicate、恢复裸 `is_deleted=false`、新增未登记 route、登记 symbol 失效均红在预期断言并逐字节还原。（AC-15、AC-16 的闭集部分，AC-23 的 B 部分，AC-24）

- [ ] 12B. 账套导入单位开发文档（R10）
  - 新建 `docs/reference/ledger-import-unit-normalization.md`：账套入口/同步 POST 410/base UUID+unit digest、四表与 AccountChart 可见性/attempt 恢复、shared PG READ ONLY inspector；display-preferences.md 只加一行链接。
  - 文档守卫核对导入 API/错误码、入口与读取 registry 和代码；真实 PG 禁写与后续批次如实列出。（AC-26 的 B 部分）

- [ ] B-V. 阶段 B 运行时冒烟/验证
  - 按 A-V 同一口径跑本阶段单元、TestClient 与 PG 集成测试（连 PG 的用例串行，`tests/procedure_delegation` 只按文件点名）、11B 守卫、vue-tsc 与逐点变异。共享 PG 只运行任务 9 的只读 inspector dry-run（输出放 tmp），隔离 PG 故障注入 UPDATE 得到 SQLSTATE 25006。
  - 用 13A-1 与 13A 从阶段 B 候选树启动独占端口，DDL 落库前核对只含 B 组迁移；只在名称含【测试】的项目上冒烟 preview 单位摘要→确认→submit→激活后两页显示 normalized_v1 存储元/因子，旧同步 POST 与旧 incremental apply 返回 410（导入中 staged 不可见由上一条 PG 集成测试证明）；finally 走平台路径回滚/删除本次数据集并核对四表与科目表行数、hash。不运行真实 apply/rollback。

- [ ] B-BK. 阶段 B 备份 commit 对象
  - 方法同 A-BK，树内含截至阶段 B 的全部本任务改动块；OID 写入当前工作流目录并核验，随后向父会话发阶段 B 进度消息。

## 阶段 C：正式导出单位策略

> 依赖阶段 A 的任务 3（`projects.amount_unit`）、6A（measure 合同、catalog 与稳定 ID）、7、11A、13A-1、13A；6C 需要任务 10 的 `ExportUnitRegion`，与 10 的附注路径子项同批完成。

- [ ] 1C. 阶段 C 基线复算与 C 组迁移（R9）
  - 按 1A 同一三处现扫重新取号，C 组号必须大于 B 组已用号；经同一只读入口现算 export_tasks、Word 版本与底稿内容版本状态，并现算正式导出调用方与前后端文件 sink 作为任务 10/11C 的基线；更新 ownership。
  - 动态创建 C 组 V/R 配对并登记 ORM/response schema：新增不可变 `custom_workbook_unit_authorities`；为 export_tasks 增加 export_year/document_types/unit_policy_snapshot，为 `word_export_task_versions` 增加 policy pair，为 `working_paper_content_version` 增加 surface class/policy pair/source storage unit 互斥证据。DDL 幂等，新写路径禁用单数 document_type。
  - R_C 在任何 DROP 前以 `RAISE EXCEPTION` 检查：任一 custom authority 行、Word policy 证据、底稿内容版本 surface/unit 证据、export task 年度/policy/多元素/非法 JSON/与旧列冲突均阻断并整单回滚；仅纯旧空镜像或可先回填旧 document_type 的单元素行可通过。补 PG/SQLite CHECK、重复迁移号、schema drift、旧任务回读，以及多文档/仅年度/仅 policy/Word policy/底稿版本证据/custom authority/单元素回填/纯旧镜像逐类回滚保护测试；候选树证明本组 schema 变更不改账套金额。（AC-21 的 C 组部分）

- [ ] 10. 模板 authority、正式 Excel/Word/PDF、组合包与归档消费者收口（R9）
  - 复用 6A 注入的单体稳定 table_id 与合并 UUID；创建标准 export_unit_policy sidecar/schema，逐四版声明 default/table units。扩展 manifest loader/validator `--check`，证明每 region 恰一 authority、ID/标签/kind/ratio scale 有效；自由文本不参与推断。
  - 自定义 workbook 改两阶段可达链：保留 ingest只收文件并返回 artifact/hash；新增 artifact preflight、hash+preflight CAS 的 unit-authority PUT、真实 finalize、ACTIVE publication instantiate路由。扩展 mapping region稳定身份/measure kind；CustomIngestionWizard实现上传→预检→逐amount region确认→finalize→绑定本项目底稿，结构漂移清确认并重做。instantiate事务写WorkingPaper/instance与authority行；旧 `/api/custom-templates` ID不能进入正式实例化。HTML/离线上传/OO新字节重跑preflight，结构不变才rebind新hash，漂移阻断并回向导。
  - 实现结构化 ExportUnitPolicy、canonical snapshot/digest与只读preflight；TrialBalance detail/summary/bulk共用exporter，单张报表与整套同源，底稿HTTP+WpExportEngine显式传policy，useAuditSheetTable可归档导出改走该后端。给审计报告五个财务placeholder登记稳定region/kind，`ReportBodyService.fill_placeholders`无默认必传policy，报告生成/full executor/组合包/PDF逐跳传入。
  - 收口附注全部路径：`export/export_with_meta/_export_template_mode_with_meta`、deliverable/full executor、普通/clone 与 refresh 逐跳显式传 policy/kinds/scales（两条表格内核的 kind/scale 消费见 6C，同批完成）。所有有文件的 disclosure 版本不论 created_via 都须有效 snapshot+digest pair；OnlyOffice 打开前验底版、回调只按 base_version_no 继承且禁止读当前 policy，refresh 继承，整份 rebuild 才建新 policy；DB pair CHECK 与 generate→OO→refresh/项目单位并发变化测试守护。
  - 收口组合与copy消费者：ExportPackageService四类来源用真实exporter、去空bytes/placeholder且policy/source错误整包失败；archive inventory对交付件绑定exact latest version/hash/policy。普通底稿必须解析current Workpaper content representation/version/artifact，formal验policy pair，data_exchange验source unit与文件marker，custom再验authority；历史金额文件无证据阻断。manifest写版本、hash、classification、policy digest或source unit。
  - 建立从前端 XLSX 和后端 Office/PDF/ZIP 实际 sink双向反查的 `EXPORT_SURFACE_REGISTRY`；每个出口恰一 formal/data_exchange/template/non_amount分类。`useExcelIO`数据 API必传surfaceId；合并试算/差额/附注数据固定输出原始元值、可见非正式说明与 `_GT_EXPORT_META`，模板/非金额用可执行谓词。修 PDF strict DTO/对象门/真实来源/内存密码/PDF-only，并在真实 `middleware/error_handler.py` 对 create路由全部validation error结构化删除input/context；marker覆盖空/超长/错误类型/额外字段。PDFExportPanel 删除“报表语言”选择器与 `exportLanguage` 状态，组件测试断言该选择器不存在，不做双语 PDF（第三轮评审 NIT）。逐sink、逐placeholder、逐custom阶段、逐归档证据和密码redactor做故障注入。（AC-19~AC-22，AC-23、AC-24 的 C 部分）

- [ ] 6C. 附注 Word 普通/clone 路径消费 kind/scale（R6、R9；依赖任务 10 的 `ExportUnitRegion`，与其附注路径子项同批）
  - `NoteWordExporter._render_table` 与 `note_template_table_look.render_cloned_table` 接收同一 `ExportUnitRegion + column_kinds + column_ratio_scales`，kind/scale 取自 6A 的 catalog 与稳定 column_id，只有 amount 执行 policy divisor；`note_template_block_fill.rebuild_block` 按 `<section_id>/<table_id>` 取 region 后交给两条内核。
  - 用 0.2 fraction 与 20 percent_points 双夹具测普通 Word 与 clone Word，四版附注两条路径结果一致；删 clone scale、互换 ratio_scale 的 Word 夹具变异均红在预期断言。（AC-11 的 Word 部分、AC-20、AC-24）

- [ ] 11C. 正式导出出口闭集接入唯一守卫（R9、R10）
  - 把任务 10 的 `EXPORT_SURFACE_REGISTRY` 接入唯一守卫：前端 XLSX 与后端 Office/PDF/ZIP 实际 sink 与登记双向相等，每个出口恰一 formal/data_exchange/template/non_amount 分类，未分类、重复分类、失效谓词或 formal 读取 displayPrefs 均以 `SCAN_SCOPE_DRIFT` 或对应机器码失败；核心 symbol manifest 补入 Trial/Report/Note/WP/PDF 前端正式导出触发函数与 `prepareFormalExport`，`export_surface_results` 自本阶段起为必含键。
  - 正反 fixture 与磁盘变异：新增未分类 sink、重复分类、删分类谓词、formal 引入 displayPrefs 均红在预期断言并逐字节还原。（AC-20 的闭集部分、AC-23 的 C 部分、AC-24）

- [ ] 12C. 正式导出单位开发文档（R10）
  - 新建 `docs/reference/formal-export-unit-policy.md`：standard/custom 两阶段 authority、四类 export surface、审计报告 placeholder、普通底稿/Word 版本证据；示例不得靠自由文本猜模板单位；display-preferences.md 只加一行链接。
  - 文档守卫核对导出 caller 矩阵与代码；外部依赖与 503 降级如实列出。（AC-26 的 C 部分）

- [ ] C-V. 阶段 C 运行时冒烟/验证
  - 按 A-V 同一口径跑本阶段单元、TestClient 与 PG 测试、sidecar 与 measure catalog `--check`、11C 守卫、vue-tsc 与逐点变异。
  - 用 13A-1 与 13A 从阶段 C 候选树启动独占端口，DDL 落库前核对只含 C 组迁移；在名称含【测试】的项目上下载并解析正式 Excel/Word/PDF：个人单位 yuan/wan 切换不改变产物，项目单位改变后数值与标签按同一 divisor 改变，data_exchange 文件含说明与 `_GT_EXPORT_META`，PDF 面板不再有“报表语言”选择器；finally 恢复项目单位并核对。LibreOffice 缺失时直接 PDF 验收保持未完成。

- [ ] C-BK. 阶段 C 备份 commit 对象
  - 方法同 A-BK，树内含截至阶段 C 的全部本任务改动块；OID 写入当前工作流目录并核验，随后向父会话发阶段 C 进度消息。

## 终验

- [ ] 13. 候选树验证、Playwright、独立评审与交付（R10）
  - 按域运行后端 pytest、前端 vitest、唯一格式 CLI/ESLint；候选树与同一 HEAD 比较 pytest/vitest/vue-tsc 失败集合，归一绝对路径。注入 TS2322及受控测试失败证明命令真运行，不把 OOM/解码/空输出报成通过。
  - 完成全部受跟踪的产品/spec/INDEX更新后，用 13A-1 工具以私有index生成candidate commit/tree并锁定 `tmp_global_display_settings/verify_wt` 分离头worktree；只从该树启动独占非3030/9980服务，Playwright 建会话前要求 expected=actual=验收清单 tree OID，错误worktree变异必须红。
  - 版本化 fixture/tool 只接受【测试】standalone+consolidated 项目和两个已批准账号，幂等准备企业树父子关系、A/B 项目成员关系、六页稳定 10000 原值及 LedgerPenetration 超过 1000 行的受控序时账（进入 el-table-v2 分支，design §16 F10），并记录对象 ID/before hashes；HTML 底稿样本为 D1 底稿「附注上市」页签（`D1TabDisclosure`，design §18 H1④⑥），DisclosureEditor 与合并附注样本所在表必须 `measure_status=matched`，不是则换一张 matched 表、不改规则（design §17 G5③）。Playwright 覆盖 Dashboard、TrialBalance、ReportView、DisclosureEditor、HTML 底稿、合并页、LedgerPenetration的 computedStyle、元→万元、刷新/重登/账号隔离、density/fixed、dataset 与正式下载；finally 按 run manifest 经平台路径恢复/删除并对账。缺账号/项目/LibreOffice/独占服务时保持未完成，禁随机数据或 DOM 注入。
  - 完成 AC-01~AC-26追踪、全部逐点变异与独立代码评审；复核router_registry、V/R、service flush/router commit、账套入口闭集、base token三次CAS、四表reader闭集、AccountChart可见性、attempt清理/激活事务、custom五步可达链、export surface四分类、审计报告placeholder、普通底稿/交付件copy evidence、Word pair、PDF 422脱敏、shared PG只读、无字体依赖、无真实PG apply、无并发块覆盖。
  - 不推送。终验后再次确认detached worktree无受跟踪变化；任何后续spec/INDEX或代码变化都重建candidate并重跑对应门。仅并发状态允许且候选树全绿时创建一个本地提交，最终commit tree OID必须逐值等于受测tree；否则保留改动并报告。未清遗留或未授权真实迁移不得标completed。（AC-01~AC-26）