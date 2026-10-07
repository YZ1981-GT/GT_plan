# 公式推送全科目接入（平台化 + 分批铺开）

## 背景

用户诉求（2026-10-04）：公式管理是平台级能力，**E1 只是示例**，目标是让所有科目底稿都通过公式管理
接入「四表 / 试算表 / 调整分录 → 底稿明细表 / 审定表 / 披露表 → 附注」的自动推送与差异管控。

上游：
- `chain-closure-phase2-formula-push-engine`（引擎 + E1 canary，18/18，2026-10-04 真实立即推送已验收）
- `chain-closure-phase3-push-rollout`（入库 / 注册表单一真源 / 单一确认点 / 审定数分量 / 附注交接；
  其 Task 13「K1 binding」为 `[-]`，**由本 spec 接手**，见需求 1）
- 已归档且 100% 完成的公式平台 spec（本 spec 只消费、不重做）：`formula-management-library`（预设库 92/92）、
  `formula-runtime-convergence`（18/18）、`formula-management-runtime-closure`（18/18）、
  `workpaper-page-formula-toolbar-closure`（F-SHELL 唯一入口 17/17）、`formula-engine-unification`（20/20）

## 术语

- **主编码**：底稿编码的 `^[A-Z]\d+` 段（`K1-1` 的主编码是 `K1`）；推送 binding 按主编码登记。
- **接入等级**（本 spec 定义，后续统计一律用它，禁止把低等级说成「已接入」）：

| 等级 | 含义 | 判据（全部现算） |
|---|---|---|
| L0 入口 | 能从该底稿打开统一公式管理 | 宿主经 `open-formula-manager` 打开 ThreeColumnLayout 的唯一 `FormulaManagerDialog` |
| L1 可见 | 公式可查看、可解释 | `prefill_formula_mapping` / `wp_formula` / 预设库有该主编码的条目 |
| L2 打开预填 | 打开页面时后端下发四表数据、前端种子 | 渲染策略输出预填载荷；**不落库、不随四表变化刷新**，不计入推送覆盖 |
| L3 推送 | 事件驱动写入业务值 | binding 已注册 + 规则已登记 + 真 ORM 集成测试通过 |
| L4 闭环 | L3 + 附注交接 + 前端独占键 + 双侧对拍 + 浏览器验收 | 见需求 9 的验收矩阵 |

## 现状实证（2026-10-04 现读 / 探针现算 / 真库现查；计数均为现算值，禁写死进判据）

| 编号 | 事实 | 口径 / 证据 |
|---|---|---|
| S1 | 分母：有科目映射的主编码 **89**（D8 E2 F6 G15 H11 I6 J3 K14 L9 M10 N5），其中 `is_primary` **72** | `wp_account_mapping.json` 按主编码去重 |
| S2 | 专用宿主组件 **81**；函证中心 6 个（E0/F0/G0/H0/K0/L0，`confirmation-hub`）；无 componentType 2 个（D0、F4 主编码） | `wp_code_overrides.json` × 前端 registry entries |
| S3 | **L3 只有 E1**：binding 注册表只登记 E1，规则 30 条（源值 7 / 派生 22 / 附注 1），全部 `E1.*` | `formula_push/bindings/__init__.py` · `formula_push_rules.json` |
| S4 | 真库推送记录：运行 1 条、目标状态 38 条，**全部 E1**（2026-10-04 用户授权的真实推送） | `formula_push_run` / `formula_push_state` |
| S5 | L2 打开预填：89 码中 **73** 码的渲染策略有预填 / 种子出口（`adjudication_prefill` 42 码最多；调用 Tier A transient seed 的 19 码 = D1~D7 / H5~H10 / I1~I6，渲染期写快照、不落库；L1~L8 经 `render_support`；K8~K13 经共享 `pl_render`）；**16** 码无出口 = 函证中心 5（F0/G0/H0/K0/L0；E0 有一个 `_prefill` 键）+ D0 + H3（只下发 `tb_values` 核对值）+ J3（股份支付，渲染策略**不取四表**）+ M3~M10 8 码（只下发 `trial_balance` 原始余额） | 探针 `_fp_prefill_probe.py`（字面量键 + 下标赋值 + 共享出口三种口径） |
| S6 | L2 有灰度开关且部分**默认关**：`LMN_FOUR_TABLE_EXTRACTION_ENABLED=False`（L1~L8 与 M1/M2 经 `_lmn_tb_helper`，关闭即全 0）、`F2_FOUR_TABLE_EXTRACTION_ENABLED=False`；D 循环两个开关代码默认 False、本机 `.env` 开启 | `config.py` + 运行时 settings 现读 |
| S7 | Tier A 预设 18 码 21 条锚点（D1~D4、D6、D7、H5~H10、I1~I6；D5 已移除、渲染策略仍调用 seed 但无预设），目标是 `checklist_responses.item_id`；全部只用 `TB()`，其中 **4** 条用了推送禁用列名 `'审定数'`（D4-1 两条、H10、I6），D1 / D2 是「原值 − 坏账」两项差；真库 21 个锚点键只在重药控股安徽 D4 与一个 E2E 测试项目上存在（各 2 行） | `d_cycle_extraction_presets.json` · 探针 `_fp_tier_a_probe.py` · 真库 |
| S8 | `prefill_formula_mapping` 覆盖 89 码 / 1402 个格；附注同步注册 78 码；前端 `build*SyncPayload` 覆盖 56 码 / 66 个函数 | 探针现算 |
| S9 | 严格取数（`strict` 参数，失败上抛不降级）只有 E1 的取数链有；其余渲染策略取数一律 fail-open（失败返回空 / 0） | 渲染策略现读 |
| S10 | **K1 半接入回归**：前端（commit `a1ea8d27b`，2026-10-03）已把 K1-1 的 42 个键（性质行 / 组合行的期初与未审 36、与报表核对 3、审定合计 3）列为「后端独占」并在保存时过滤，但后端没有 K1 binding ⇒ 这些键**没有任何持久化写入方**：「从 K1-2 同步未审数」「从四表带入」写的 `-begin/-unadj` 与审定合计、用户手填的「与报表核对」三项（`el-input-number` 可编辑）都只改内存、刷新即丢；AI 复核上下文（`cycle_review_context`）按持久化值读 `K1-1-audited-receivable`，也读不到新值 | `k1BackendOwnedKeys.ts` · `GtK1OtherReceivables.handleChildSave` · `K1TabAdjudication.vue` |
| S11 | S10 尚未造成真实数据损失：真库 K1 底稿 5 张，前端切换后 K1 条目写入 **0** 行；唯一有数据的重药控股安徽 K1 停在 2026-07-25（独占键 11 条） | 真库 |
| S12 | K1 独占键另有第二写入方：K1-1 导入 handler 直接写 `K1-1-fs-*` 与组合行 `-unadj` | `_k1_import_export._k1_1_import_handler` |
| S13 | K1 键名漂移：坏账明细页读 `K1-1-audited-bad-debt`，全仓写入方只写 `K1-1-audited-baddebt` ⇒ 该页「与审定表一致」恒按 0 比对；真库前者 0 行 | `K1TabBadDebtDetail.vue` |
| S14 | **防抖合并丢事件（实测）**：EventBus 去重键 = `事件类型:项目:年度`，不含 `wp_id`；500ms 内两张不同底稿的 `WORKPAPER_SAVED` 经 `publish` 只派发最后一张（`publish_immediate` 不合并）。底稿条目保存（`checklist-responses` PUT）走 `publish` ⇒ 多张底稿接入后会丢推送 | 探针 `_fp_dedup_probe.py` 实测 delivered=1/2 |
| S15 | 四条 `after_save` 路径中 HTML 保存 / Univer 保存 / OnlyOffice 回调的事件载荷**不带 `wp_code`**（只有自定义查询回写带）；推送触发器按 `extra.wp_code` 过滤 ⇒ 这三条路径保存不触发派生重算。`WORKPAPER_SAVED` 现扫 19 处订阅（跨行容忍的字面量口径），其中只有 A13 有按 `wp_id` 反查兜底 | `workpaper_save_orchestrator` 调用方现读 · 探针 `_fp_subscriber_probe.py` |
| S21 | 前端直写 `checklist-responses`（PUT）的文件 **241** 个 / 调用 **275** 处；共享持久化层 `useChecklistPersistence` 只是其中一种写法 ⇒ 只在前端过滤独占键**不可能完整** | 探针 `_fp_subscriber_probe.py` |
| S22 | **S14 同一根因吞掉「发布到试算表」的确认**（实测）：发布门端点以防抖 `publish` 发出带 `publish_confirmed=True` 的 `WORKPAPER_SAVED`（载荷无 `wp_id`）；若 500ms 内同项目同年度再来一次条目保存，确认事件被整体覆盖 ⇒ 试算表不更新，而端点已返回成功、界面提示「已发布」。现扫「发布后在同一函数内立即保存条目」的站点 **2** 个：K6（立即保存，当前即受影响）、K1（2026-10-03 起被 K1 独占键过滤**意外挡住**；需求 1.8 的回退会让它复现）。真库 `tb_publish_ack` 只有 D4-1 的 8 条，K1 / K6 为 0（与「被吞」一致，但也可能是没人用过，不作因果结论） | 探针 `_fp_publish_race_probe.py`（间隔 50 / 300ms 确认丢失、600ms 保留）· `_fp_publish_then_save_probe.py`（最内层函数口径） |
| S16 | 面板多科目缺口：`/states`、`/latest` 不按底稿过滤，`/run` 不接底稿参数 ⇒ 第二个 binding 接入后，面板会把别的科目的差异显示在当前科目下，「立即推送」会推全部科目 | `routers/formula_push.py` · `panel.py` · `FormulaPushPanel.vue` |
| S17 | 引擎写死 E1 的位置：四表槽名 `FOUR_TABLE_SLOTS`（E1 的 cash/bank/…）、附注章节表 `_SECTION_MAP`（只有 五、1 / 八、1）、附注字段 `NOTE_FIELDS`（只有期末 / 期初两列）、主表骨架 `build_main_skeleton`（只认上述章节） | `rules.py` · `note_writer.py` |
| S18 | 前端「推送提示条」两套口径：E1 按前缀 `E1-` 过滤 changed_items，K1 按独占键过滤 | `e1FormulaPushNotice.ts` · `k1FormulaPushNotice.ts` |
| S19 | 推送取数的试算表上下文只装「期末余额 / 年初余额」两列；`TB(code,'本期发生额')` 取不到列时返回 0 并记 trace（不报错）⇒ 损益类科目直接照搬 E1 规则会**静默推 0** | `sources.FormulaSources.context_for` · `formula_engine._resolve_tb_column` |
| S20 | 数据分布：真库 D~N 主编码底稿 412 张（87 码 / 39 项目），条目 ≥10 的只有 **18 张**（18 码）。另有**子码分册**底稿 1214 张（5 个真实项目 + 1 个 E2E 项目，主要来自两个各 567 张的项目），其中 14 张有条目（40 行）：D2-1、H1-1、F1-2、F2-22~29、I2-1、D4-33、G1-3 等直接把条目写在子码分册上，而推送引擎只按主编码找底稿（`_find_workpapers`）⇒ 这些条目推送看不见。E1 / K1 现无此情况（5 个项目的条目全在主编码底稿） | 真库 |

## 需求

### 需求 1：K1 补齐后端写入方（P0，修回归）

**用户故事**：作为审计助理，我在 K1-1 点「从 K1-2 同步未审数」或手填「与报表核对」三项后刷新页面，数据还在。

#### 验收标准
1. THE K1 binding SHALL 注册进推送注册表；K1 独占键集合 SHALL 收敛为规则派生集合（预期只剩审定合计 3 键，见 design §八），SHALL NOT 存在「前端标为独占、后端无规则」的键。
2. WHEN 四表入库或试算表重算 THEN 性质行 n0~n4 原值与账龄组合 r1 的期初 / 未审数 SHALL 作为**可编辑**目标推送（与渲染预填同口径）；其余组合行（r0/r2/r3）与性质行坏账四表无口径，SHALL NOT 推送；审定合计（原值 / 坏账 / 净值）SHALL 为派生目标、由后端写入。
3. 「与报表核对」三项 SHALL 是可编辑目标（三态：用户手填保留、等于上次推送值则跟随），SHALL NOT 列为系统值；用户手填 SHALL 能持久化。
4. 「从 K1-2 同步未审数」「从四表带入」两个按钮写入的都是可编辑键，SHALL 照常持久化（推送将其记为人工值，面板可「采用公式值」）；SHALL NOT 继续「写内存、刷新即丢」。
5. K1-1 导入 SHALL 不再直接写后端独占键：系统值 / 派生值由导入后触发的推送重算；可编辑目标照常写入并记为人工值。
6. 坏账明细页 SHALL 读取真实写入的审定坏账合计键（修 S13 键名漂移），并加守卫：页面读取的 `K1-1-audited-*` 键必须有写入方。
7. 取数 SHALL 用 strict 模式；舍入对齐前端 `Math.round(n*100)/100`；双侧夹具对拍。
8. THE 止血 SHALL 分两步且顺序不可颠倒：①先修事件总线（需求 2.1、2.6），②再把 `k1SaveItemIds` 恢复为不过滤（前端照常写全部键，回到 2026-10-03 前状态）——反过来做会让 K1「发布到试算表」重新被吞（S22）。K1 binding 与独占键强制（需求 4.3）都上线后再收紧；任何时刻 SHALL NOT 存在「用户能操作、却无人持久化」的键。

### 需求 2：多科目并存的触发正确性

#### 验收标准
1. WHEN 两张不同底稿在防抖窗口内先后保存 THEN 推送 SHALL 对两张都执行；不同 `wp_id` 的保存事件 SHALL NOT 互相合并（S14）。S14 影响全部订阅者，SHALL 在事件总线去重键修复（不只修推送一侧）；变更前 SHALL 列出 19 处订阅逐个评估，同一底稿的连续保存 SHALL 仍合并。
2. THE 推送触发器 SHALL 能识别所有写入路径的底稿保存：事件缺 `wp_code` 时按 `wp_id` 反查主编码，而不是静默不推（S15）。
3. 子码保存（如 `K1-1`）SHALL 归到主编码 binding（`K1`）；不在注册表的主编码 SHALL 不推。每个接入科目在 canary 前 SHALL 现查真库：条目落在主编码底稿还是子码分册（S20）；落在分册的，binding SHALL 明确「推哪张底稿」（主册 / 分册 / 拒推并报原因），SHALL NOT 静默只推主册。
4. WHEN 一次运行内某个 binding 取数失败 THEN 该底稿 SHALL 零写入并记失败，其余已接入底稿 SHALL 照常推送（失败隔离到底稿级，现状是整次运行失败）。
5. 事件触发的推送 SHALL 只跑与事件相关的 binding（科目前缀相交 / 被保存的底稿），SHALL NOT 每次事件跑全部 binding。
6. 带确认语义的事件（「发布到试算表」的 `publish_confirmed=True`）SHALL NOT 被防抖合并覆盖（S22）；守卫 SHALL 复现「发布后 50ms 内紧接一次条目保存」并断言两个事件都派发、试算表被更新。

### 需求 3：面板与接口按科目隔离

#### 验收标准
1. `GET /states`、`GET /latest` SHALL 支持按主编码过滤；公式管理「公式推送」页签 SHALL 只显示当前底稿的规则、运行与差异。
2. `POST /run` SHALL 支持只推指定主编码；页签内「试跑 / 立即推送」SHALL 默认只作用于当前底稿；项目级「全部推送」SHALL 是单独入口并显示将影响的底稿清单。
3. 运行记录 SHALL 带每张底稿的结果（已有 `detail.wp`），面板「最近推送」SHALL 显示当前底稿那一段，而不是整次运行。
4. 权限保持：查询 readonly、写入 edit（端点级真请求测试覆盖新增参数）。

### 需求 4：后端独占键单一真源

#### 验收标准
1. 每个已接入主编码的「后端独占键」SHALL 由规则清单生成，范围 = `policy ∈ {system, derived}` 的底稿目标；`editable` 目标（用户可编辑、后端三态写入）SHALL NOT 进独占集合（K1「与报表核对」三项被误列为独占正是 S10 的直接原因）。产物进前端生成文件，SHALL NOT 由各科目手写正则。
2. 生成器 SHALL 输出幂等（内容不变不改时间戳）并有 `--check`；CI 用 `--check` 判漂移。
3. **单一写入方 SHALL 在后端写入口强制**：`checklist-responses` 批量保存 SHALL 对已接入主编码的独占键不落库，响应体列出被跳过的键（`skipped_owned_keys`）并计数日志，使 S21 的 241 个前端直写点无需逐个改造即满足「一个单元格一个写入方」；SHALL NOT 拒绝整批（其余键照常保存）。
4. 前端共享持久化层（`useChecklistPersistence`）与 E1 / K1 宿主 SHALL 按生成集合预先过滤（减少无效请求、避免「保存成功」的误导提示），其余宿主随各批接入时改；前端过滤是优化，正确性以需求 4.3 为准。
5. E1 迁移有一处**预期内的行为变化**须显式登记：E1 明细合计（`E1-*-detail-*-unaudited`，规则策略为派生）今天由前端 composable 与后端同式双写，迁移后只由后端写入（页面内存照常同式计算）；以双侧夹具证明持久化值不变，并先现扫这些键的后端读方。
6. 后端其余写入方（导入 handler、OnlyOffice 同步回写等）写已接入主编码独占键的站点 SHALL 冻结为基线、只许减少；同步契约里映射到独占键的单元格 SHALL 是公式 / 只读格（守卫比对契约的公式掩码）。
7. 守卫 SHALL 双向：①前端生成集合 == 后端规则现算集合 ②前端任一宿主读取的独占命名空间键都有后端规则（防 S13 型漂移）。
8. 推送提示条 SHALL 统一为一个纯函数，按「本次 changed_items ∩ 当前底稿独占键」判定（消除 S18 两套口径）。

### 需求 5：规则与 binding 通用化（去 E1 写死）

#### 验收标准
1. 四表槽名 SHALL 由各 binding 自报，规则校验按 binding 校验 `slots`（S17）。
2. 附注章节 SHALL 由规则自身声明（已有 `section_by_template`），`note_writer` SHALL NOT 写死章节表；主表骨架 SHALL 按规则声明的章节与表名从附注模板生成。
3. 附注写入字段 SHALL 由规则声明（期末 / 期初 / 本期 / 上期 …），SHALL NOT 只支持两列；未声明字段一律不写。
4. 试算表取数上下文 SHALL 支持损益类发生额口径（与报表引擎审定模式同口径），规则校验 SHALL 拒收「用了上下文未装载的列」的公式（防 S19 静默推 0）。
5. 派生名 SHALL 按 binding 限定校验：A 科目的规则不能引用 B 科目 binding 实现的派生。
6. 新增一个科目 SHALL 只需：新建 binding 模块 + 注册表一行 + 规则清单若干条 + 测试；其余文件零改动（以临时注册假 binding 的测试证明，沿用 phase3 的 Z9 判据并扩展到附注与独占键）。

### 需求 6：接入等级清册与守卫

#### 验收标准
1. THE 平台 SHALL 有一份生成式清册：逐主编码列出 L0~L4 等级、是否有专用宿主、渲染预填形态（含灰度开关**名**）、binding / 规则数、附注同步注册、前端同步载荷、「不适用」原因。灰度开关现值与真库底稿数随环境 / 数据变化，SHALL NOT 写进清册文件（否则 `--check` 成永假门禁），由面板运行时展示、由各批验收现算记入证据栏。
2. 清册 SHALL 由脚本现算生成（`--check` 幂等），SHALL NOT 手写；分母口径 = 需求术语表。
3. 守卫 SHALL 钉死：L3 集合 == 注册表集合；L3 主编码必须有真 ORM 集成测试文件；声明 L4 的主编码必须满足需求 9 全部判据。
4. 「公式管理」页签在未接入推送的底稿上 SHALL 显示中文说明「本底稿尚未接入自动推送（当前等级：L?）」，SHALL NOT 静默隐藏。

### 需求 7：分批铺开（按底稿形态分族，不按字母）

#### 验收标准
1. 每批 SHALL 先做 canary（一个科目走完 L4），canary 验收通过后同族其余科目才能接入。
2. 批次与族划分（实施前现算复核）：
   - **批 A｜K1**（需求 1，P0）
   - **批 B｜Tier A 单公式族**：S7 的 18 码 21 条锚点迁为 `source/formula` 规则（试算表核对行），canary 取一个有真实数据的码
   - **批 C｜资产负债类审定表族**：K2~K7、G1~G10、H1~H10、I1~I5、J1~J2 中「期初 / 未审 / 审定合计」结构的审定表；按共享规格（如 `KCycleSpec`）做**族 binding**，SHALL NOT 每科目复制一份 E1 式 binding
   - **批 D｜损益类发生额族**：K8~K13、G11~G14、L8、N4、N5 等（依赖需求 5.4）
   - **批 E｜明细行集族**：D 循环、F 循环、E1 以外的明细行种子（依赖需求 5.1，行身份须稳定）
   - **批 F｜L / M / N**：依赖 `LMN_FOUR_TABLE_EXTRACTION_ENABLED` 的取数链先修成 strict 可用（需求 8）
3. 同一推送目标 SHALL 只属于一个批次：批 B 只接 Tier A 锚点（试算表核对行），同一底稿的其余目标归其形态族（如 H8 的核对行在批 B、审定表其余行在批 C）。
4. 每批 SHALL 单独立 spec（或在本 spec 追加批次节），引用本 spec 的需求编号，不复述。
5. 函证中心（6 码）、程序表、检查表、文档型底稿 SHALL NOT 接入推送（无会计口径写入目标），清册中标为「不适用」并写明原因。

### 需求 8：取数严格化

#### 验收标准
1. 推送用到的每条取数链 SHALL 提供 `strict` 关键字参数（缺省 False，渲染行为逐字不变）；推送一律 strict。
2. 灰度开关关闭时，推送 SHALL 报「该科目四表取数未启用」并跳过，SHALL NOT 把全 0 当成取数结果推送（S6）。
3. 每条 strict 取数链 SHALL 有「失败 ⇒ 零写入 + 失败运行记录 + sync.failed」的真 ORM 测试。

### 需求 9：每个科目的 L4 验收矩阵（横切）

#### 验收标准
1. 规则清单校验通过且目标唯一；binding 单测覆盖目标展开 / 叠加层 / 附注行。
2. 前后端双侧夹具逐值对拍（字符串逐字、浮点逐位）；任一侧改算式必红。
3. SQLite 真 ORM 集成：四表变化 → 底稿 → 审定合计 → 附注；人工值保留；锁定保留；冻结底稿跳过；取数失败零写入。
4. 关键 SQL 段真 PG 验证（一次性 schema）；真实项目只在事务内试跑并回滚，前后指纹逐字相同。
5. 端点真请求覆盖新增参数与权限；前端真挂载覆盖页签、提示条、独占键过滤。
6. Playwright 真浏览器：页签、试跑、提示条、附注数值；真实「立即推送」写库须经用户同意，未经同意记 `[ ]*`。
7. 每项修复有变异证明（改回即红），「零 / 非零」判据配反向样本。

## 非目标

- 试算表未审数改为公式驱动（phase3 决策 4 已否决）。
- 重做公式编辑 / 预设库 / F-SHELL 入口（已归档 spec 已交付）。
- 函证中心、程序表、检查表、文档型底稿的推送。
- 本 spec 内不铺开批 C~F 的具体科目实现：本 spec 交付平台化（需求 2~6、8）+ 批 A + 批 B canary；其余批次按需求 7.3 另立。
- phase3 尚未完成的任务（审定数分量写入函数、真库试跑、Playwright）仍归 phase3。
