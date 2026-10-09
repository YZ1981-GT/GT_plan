# 实施计划：披露表 → 附注 同步载荷的权威源归属

> 关联需求：#[[file:.kiro/specs/disclosure-payload-authority-source/requirements.md]]
> 关联设计：#[[file:.kiro/specs/disclosure-payload-authority-source/design.md]]
> 任务约定：`[ ]` 未开始 / `[x]` 完成 / `[ ]*` 可选或待外部环境。
> 铁律：先扫不改得现算基数 → 再改 · 判据禁写死行号与宿主清单 ·
> 结构性零必配双向变异 · 只读端点必注册 `router_registry` ·
> FastAPI 不热加载（改 router 后重启 `start-dev.bat`）· PBT `max_examples=5`。
> **本 spec 第一产出是裁定（阶段 0），未经确认不得进入阶段 1。**

## 阶段 0：方案裁定确认（Design-First 关口）

- [x] 0.1 现算三方案规模基数（脚本产出，禁引用代码注释旧值）
  - `buildXSyncPayload` export 定义数 · `syncToDisclosureNotes` 宿主文件数 ·
    `useDisclosureAutoSync` 实现数与调用点数 · 被调用未见定义的名字
  - 与设计 §一 表格逐项对账；有偏差则更新设计而非沿用
  - 🔴 反例锚定：`GtWpDisclosureSyncBar.vue` 文件头「46 个」现算为 **69**，注释已过期
  - 🔴 **本任务已交付但结论被勘误**：交付时把现算值记成 109，第四轮穷举 120 种口径组合无一命中，真值 **69**（export 定义 69 / 去重名字 67）。宿主 117 vs 112 是口径差异（两者都对），调用点 146→144→154 属漂移禁写死。详见设计 §十四
  - _需求：1.3_ _属性：Q1_

- [x] 0.2 现查真实库覆盖率基线
  - `disclosure_notes` 总数 / `last_sync_at` 非空数 / `is_stale` 数（编写时 1052/93/225）
  - 按 `wp_code` 与变体分组看分布，识别是否集中在少数循环
  - _需求：1.3, 3.3_ _属性：Q1, Q6_

- [x] 0.3 载荷构造器纯函数性抽样复核
  - 抽样若干构造器（含位置参数形态与 options 对象形态各若干）确认：
    无 Vue 响应式依赖 / 无 `useRoute()` / 无 DOM 访问
  - 现算签名形态分布（位置参数 vs 单 options 对象各多少）
  - 该结论是 ADR-DPA-001 否决 B、延后 D 的技术依据，须实证不得推断
  - _需求：1.1_ _属性：Q1_ _ADR：ADR-DPA-001_

- [x] 0.4 输出三方案 ROI 裁定并取得确认
  - 逐方案填改动量 / 双写风险 / 可自动化 / 回归面 / 失败模式
  - 明确写「为什么不选 A」「为什么不选 B」「为什么延后 D」
  - 🔴 撤回记录：方案 B 是前序对话中提出的建议，据 0.3 实证撤回（载荷是计算非常量）
  - **裁定未确认前不进入阶段 1**
  - _需求：1.1, 1.2, 1.4, 1.5, 1.6_ _属性：Q1, Q2_ _ADR：ADR-DPA-001_

## 阶段 1：同步链缺陷全量扫描与修复

- [x] 1.1 先扫不改：全宿主缺陷普查
  - 扫全部 `syncToDisclosureNotes` 宿主（集合现算），统计两类缺陷各自命中数：
    ① 函数体内含 `useAuditContext` ② 函数体内含 `scheduleAutoSync(自身)`
  - 命中数**现算登记**；按量级决定单批还是拆批修（风险 S1）
  - 若某类现算为 0 → 必须给变异证明说明扫描器非恒绿
  - _需求：2.3, 2.5_ _属性：Q3, Q4, Q5_ _风险：S1_

- [x] 1.2 新建全宿主守卫 `disclosureSyncWiringAll.spec.ts`
  - 两条不变量覆盖全部宿主（现有 `j1DisclosureSyncWiring.spec.ts` 仅覆盖 J1 若干 Tab）
  - 宿主集合现算、禁写死清单；新增宿主自动纳入
  - **双向变异**：注入缺陷样本必败、已正确宿主必过
  - 提交时须**先红**（若 1.1 命中非零）
  - _需求：2.3, 2.4_ _属性：Q3, Q4, Q5_

- [x] 1.3 修缺陷 ①：`useAuditContext` 提到 setup 顶层
  - 🔴 **实际未改任何代码 —— 1.1 普查命中数现算为 0**（112 宿主全部已正确）。
    该缺陷已在前几轮 spec（`j1-disclosure-template-alignment` Task 10.1 等）修完。
    本轮产出 = 把不变量**锁进全宿主守卫**（1.2），防回退。
    标 `[x]` 的含义是「判据已满足且有守卫」，不是「本轮改过宿主代码」。
  - 目标形态（守卫锁死的）：setup 顶层 `const { year: auditYear } = useAuditContext()`，
    函数体内用 `auditYear.value`
  - **不动 69 个载荷构造器的业务内容**（只动上下文获取时序）
  - _需求：2.1, 2.6_ _属性：Q3_

- [x] 1.4 修缺陷 ②：去除自触发调度
  - 🔴 **实际未改任何代码 —— 命中数现算为 0**（同 1.3）。
    首版扫描器曾报「J1 两个 Tab 命中」= **误报**：那两处 `scheduleAutoSync(syncToDisclosureNotes)`
    只存在于**注释**里（源码注释正是在说明「此处不得这么写」），去注释后命中 0。
    该坑 `j1DisclosureSyncWiring.spec.ts` 文件头早有记载（「首版守卫即因此误报」）。
  - 目标形态（守卫锁死的）：`syncToDisclosureNotes` 内不 `scheduleAutoSync(自身)`
  - 保留手动按钮与自动同步**同源幂等**的既有设计
  - _需求：2.2, 4.3_ _属性：Q4_

- [x] 1.5 阶段 1 回归
  - `rtk npx vitest run` 相关目录；既有 `j1DisclosureSyncWiring.spec.ts` 作基线不得回退
  - _需求：2.3_ _风险：S3_

## 阶段 2：覆盖率可观测

- [x] 2.1 后端只读覆盖率查询 service
  - 返回按 `wp_code` × 变体分组的 `{expected, synced, stale, never_synced}`
  - 分母派生自 `note_workpaper_sync_registry.json`，**禁手工第二份清单**
  - 分母排除项目未启用底稿（启用判定走 `wp_index`，`is_deleted == False`）
  - 纯只读、不触发同步、只 flush 不 commit（实际无写）
  - _需求：3.1, 3.2, 3.5, 3.6_ _属性：Q7_

- [x] 2.2 口径对账守卫
  - service 结果与直接 SQL 统计（`last_sync_at` 非空 / `is_stale`）逐值相等
  - 双向变异：构造「有未启用底稿」场景断言其不计入分母；全启用场景分母等于注册表全集
  - _需求：3.3_ _属性：Q6, Q7_ _风险：S2_

- [x] 2.3 只读端点 + router_registry 注册
  - 新增 GET 端点；**必须**在 `backend/app/router_registry/` 对应 group 注册
  - 判据：注册缺失即前端 404；改后须重启（FastAPI 不热加载）
  - _需求：3.1_ _风险：S5_

- [x] 2.4 前端展示接入（复用既有展示位）
  - 复用 `GtWpDisclosureSyncBar.vue` 展示位 + 附注侧汇总面板，**不新建页面**
  - UI 文本全中文（技术术语保留英文）
  - _需求：3.4_ _ADR：ADR-DPA-002_

- [ ]* 2.5 Playwright 实测覆盖率面板（需 `start-dev.bat`）
  - 面板数字与 `mcp_postgres` 直查一致；点击可跳到对应披露 Tab
  - 环境不可用时如实标 `[ ]*` + 写「代码已改但未实测」，禁标完成
  - _需求：3.4_ _属性：Q6_

## 阶段 3：不变量守卫（只加守卫，不改实现）

- [x] 3.1 跨主体零写入守卫
  - 国企项目请求上市章节 → 拒绝且 DB 无任何变更（守卫须断言**零写入**而非仅抛异常）
  - _需求：5.1_ _属性：Q8_

- [x] 3.2 空载荷不清表守卫
  - 空 `sub_table_data` 同步后既有子表内容逐值不变
  - 双向变异：非空载荷必须真的改变内容
  - _需求：5.2_ _属性：Q9_

- [x] 3.3 `manual_override` 保护守卫
  - 标记字段不被联动写入覆盖
  - _需求：5.3_

- [x] 3.4 年度权威守卫
  - 同步目标年度取 `projects.audit_year`；构造「服务器自然年 ≠ 审计年度」场景断言写对年度
  - 锚定既有注释记录的事故形态：2026 年做 2025 年报审计时写错年度 ⇒ 审计师永远看不到
  - _需求：5.4_

- [x] 3.5 变体不串写守卫
  - 同一 `wp_code` 的 `listed` 与 `soe` 章节号互不串写
  - _需求：5.6_ _属性：Q6_

- [x] 3.6 注册表一致性 CI
  - 重跑 `gen_note_wp_sync_registry.py --write` 后 JSON 字节无 diff
  - 守卫注释保留该脚本记录的两个正则陷阱引用（声明锚定 / `(?![\w])` 收尾）
  - _需求：5.5_ _属性：Q10_

## 阶段 4：开关澄清与收尾

- [x] 4.1 澄清 `DISCLOSURE_AUTO_SYNC_ENABLED` 作用域
  - 在代码注释与 `.env.example` 写明：**只管后端兜底标 stale，不管前端自动同步**
  - 现算真实引用处（编写时 3 处）逐个核对注释一致
  - **本轮不改默认值**（仍 `false`）
  - _需求：4.1, 4.2_ _ADR：ADR-DPA-003_

- [x] 4.2 写明开启前置条件与降级路径
  - 前置：阶段 1 守卫全绿 + 阶段 2 覆盖率查询上线
  - 降级：手动同步按钮保留（与自动同源幂等）；失败至少标 `is_stale` 不静默
  - 失败不得反向破坏底稿保存（fail-soft 且必须留日志）
  - _需求：4.2, 4.3, 4.4, 4.5_

- [x] 4.3 核实 active 目录疑似残留空壳
  - `workpaper-page-formula-toolbar-closure` 现扫 0/0、三件套不全，归档存在同名 17/17
  - 核实后在 INDEX.md 登记说明；**不擅自删除历史目录**（档案 append-only）
  - _设计：§八_

- [x] 4.4 清理探针文件
  - 删本 spec 新增的 `backend/scripts/analyze/_*` 探针与输出
  - _设计：§十_

- [x] 4.5 交付前自查
  - 脚本化检查「每条需求 / 每条 Q1~Q10 / 每条 ADR 至少被某 task 引用」
  - 无写死行号、无写死宿主清单、无写死计数
  - 新增端点已注册 `router_registry`
  - _设计：§十_

- [x] 4.6 沉淀
  - `#dev-history` 追加：四方案 ROI 结论 + 方案 B 撤回依据 + 覆盖率基线数字
  - `memory.md` 只更新状态行（≤200 行约束）
  - 归档 spec **不回填**

---

## 判据引用闭合性对照（交付前须脚本复核）

| 判据 | 被引用任务 |
|---|---|
| 需求 1.1~1.6 | 0.1, 0.3, 0.4 |
| 需求 2.1~2.6 | 1.1~1.4 |
| 需求 3.1~3.6 | 0.2, 2.1~2.5 |
| 需求 4.1~4.5 | 1.4, 4.1, 4.2 |
| 需求 5.1~5.6 | 3.1~3.6 |
| Q1 | 0.1, 0.2, 0.3, 0.4 |
| Q2 | 0.4 |
| Q3 | 1.1, 1.2, 1.3 |
| Q4 | 1.1, 1.2, 1.4 |
| Q5 | 1.1, 1.2 |
| Q6 | 0.2, 2.2, 2.5, 3.5 |
| Q7 | 2.1, 2.2 |
| Q8 | 3.1 |
| Q9 | 3.2 |
| Q10 | 3.6 |
| ADR-DPA-001 | 0.3, 0.4 |
| ADR-DPA-002 | 2.4 |
| ADR-DPA-003 | 4.1 |
| S1~S6 | 1.1, 1.5, 2.2, 2.3（S4 由 design §九 承接、S6 由 ADR-DPA-001 承接）|

---

## 与 spec `adj-formula-repair-and-approval-gate-wiring` 的并行约定

改动文件零交集：

| | 本 spec | 对方 spec |
|---|---|---|
| 前端 | 披露 Tab 宿主 + 覆盖率展示位 | 无（仅 `FormulaTab.vue` 只读引用） |
| 后端 | 新增覆盖率只读 service/端点 · `disclosure_stale_marker` 注释 | `prefill_engine` · `trial_balance_service` · `wp_cross_check_service` · `adjustment_service` · `EventType` · 新增 `adjustment_amount_source` |
| `event_handlers/_impl.py` | **不动** | 改 approved 订阅源 |

两 spec 可并行实施，无需排序。
