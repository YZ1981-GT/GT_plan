# 致同审计作业平台 · 资深合伙人全局评估与改进建议
**评估日期**：2026-07-12
**评估视角**：审计助理 / 现场经理 / 质控复核 / 项目合伙人 / EQCR 独立复核 五角色 + 上线后运维
**评估方法**：基于代码库实测（8,993 文件 / 154k 节点 / 329k 边；715 routers + 731 services；前端 2,037 Vue 组件 + 1,439 底稿 composables），非主观臆测

---

## 〇、总体判断（一句话）

**平台"功能覆盖已经做到了行业罕见的完整度"（A~N+S 全循环底稿、四表-报表-底稿-调整-附注全链、ACNR 地址库、公式管理库、复核/抽凭/版本链基础设施都在），但"工程一致性"与"全局机制的落地率"没有跟上功能扩张的速度**。当前最大的风险不是"缺功能"，而是**"同一个全局能力有 N 套实现、新页面容易漏接全局服务、巨型文件与碎片化并存导致维护成本随功能线性甚至超线性增长"**。

下面按"最痛→次痛"排序，每条都给出**实测证据 + 五角色影响 + 具体建议**。

---

## 一、【最高优先级】全局显示偏好（单位/字号/小数/密度/负数）对底稿"名存实亡"

### 实测证据
- 平台已有一个设计完整的 `useDisplayPrefsStore`（`stores/displayPrefs.ts`，227 行）：涵盖**金额单位（万/元/亿）、字号、小数位、负数红字、变动高亮阈值、表格密度、按页固定列**，并持久化 localStorage。这是很专业的设计。
- **但底稿层几乎没有真正消费它**。抽查 D1/D2/E1 等 30+ 个底稿 tab，全部是这个写法：
  ```ts
  const displayPrefs = inject<{ fmtAmount }>('displayPrefs', {
    fmtAmount: (v) => v===0?'-':v.toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2})
  })
  ```
  而底稿主入口（如 `GtD2AccountsReceivable.vue`）`provide('displayPrefs', {...})` 提供的是**一个硬编码闭包**（固定 2 位小数、固定"元"口径、固定负数括号），**不是那个 Pinia store**。
- 结果：用户在全局设置里切"万元/字号/小数位/密度"，**报表和序时账变了，但所有底稿纹丝不动**——因为底稿走的是另一条被写死的路径。

### 五角色影响
- **审计助理**：底稿金额永远是"元 + 2 位小数"，跟审定表/报表口径不一致，核对时反复心算。
- **项目经理 / 合伙人**：复核时同一个数在报表显示"万元"、在底稿显示"元"，观感割裂，怀疑数据错。
- **运维**：将来想统一口径，要改的不是 1 个 store，而是 200+ 个底稿里的硬编码闭包。

### 建议（P0）
1. **收敛为单一真源**：底稿主入口的 `provide('displayPrefs', ...)` 直接 provide `useDisplayPrefsStore()`（或其 `{ fmt, fmtAmount, amountClass, unitSuffix, tableDensity, fontConfig }` 的响应式引用），删除硬编码闭包。
2. **建 CI 守卫**：禁止在 `inject('displayPrefs', {硬编码})` 里写本地 fallback 实现（只允许 `inject(DisplayPrefsKey)` + 类型化 InjectionKey）。参照现有 `check_wp_ref_contract.py` 的做法加一条规则。
3. **字号真正生效**：`fontConfig` 要挂到底稿根容器的 CSS 变量（`--wp-font-size`），底稿内表格统一用 `var(--wp-font-size)` 而非散落的 `font-size:13px` 硬编码（现在满仓库都是 `13px` 字面量）。
4. **单位换算要影响导出**：`unitDivisor` 已有，但要确认底稿导出 Excel 时按当前单位口径还原/标注，避免"屏幕万元、导出元"。

> 这条是"显示一致性"的根，投入不大（主要是收敛 provide + 加守卫），但对 5 类用户的**每一次使用**都有感。

---

## 二、【最高优先级】"全局能力已建好，但新页面容易漏接"——缺少强制接线机制

### 实测证据
- 本次会话就是活教材：**账龄配置**早已做成全局服务 `useAgingConfig(projectId, subject)`（aging-config-enhancement 40/40 已完成，D2/D3/F1/K1/K3/G5 明细表接了），但 **D2-5 分析程序页刚发现根本没接**，账龄段是硬编码"1年以内/1-2年..."，直到用户指出才修。
- 同类全局能力都有"接入率不齐"问题：
  - **ACNR 地址库**：`acnr-consumer-wiring` 复盘扩到 P1–P15，明确有"死代码路径/消费者未全接"。
  - **公式管理库 draft-refresh**：复盘发现 P0 曾是"空壳"（全局刷新不传 units、affected_count=0）。
  - **版本链**：`GtWpVersionTrail` 通用组件就绪，但 D2/D3~D7 多数结构化底稿未接（memory 明确记录）。

### 根因
全局服务是"**可选接入**"的——靠开发者记得去 import + 接线，没有"**默认接入 / 不接就报错**"的机制。功能一多，必然漏。

### 建议（P0）
1. **底稿骨架组件化**：抽象一个 `<GtWorkpaperShell>`（或 composable `useWorkpaperScaffold`），**默认注入**：displayPrefs、agingConfig、版本链工具栏、复核 provide、AI provide、导入导出 dropdown、审计目标/编制提示插槽。新底稿"套壳"即自动拥有全部全局能力；不套壳则 CI 报警。
2. **接入率看板 + CI drift guard**：建一张 "Global Capability Coverage Ledger"（哪些底稿接了 aging/version/review/displayPrefs/ACNR），CI 扫描"应接未接"并阻断。参照 memory 里 ACNR Coverage Ledger 的思路，推广到所有全局能力。
3. **契约测试前移**：design 文档里强制写"组件↔全局服务 契约"章节（就像 ref-unwrap 契约那样），tasks 里每个底稿有一条"接线校验"子任务。

---

## 三、【高】前端"底稿 UI 一致性"靠人肉复制，缺组件库沉淀

### 实测证据
- 本次会话反复在做：textarea `minRows:5`、导入导出 `el-dropdown`、`GtIndexChip value="wp:X"`、公式列 `auto-calc-col + formula-cell`、`opinion-card`、审计目标 `el-alert`、编制提示 `details`……这些是 memory 里明文的"底稿 UI 铁律"，**但它们是"约定"不是"组件"**，每个底稿靠开发者手抄，一抄就漏（本轮就漏了 D2-5、漏了多处 minRows）。
- 证据：全仓库 `font-size:13px` 字面量、`autosize`/`:rows="4"` 混用、`opinion-card` 样式被复制进几十个 `<style scoped>`。

### 五角色影响
- **所有角色**：不同底稿细节观感不一（框高、按钮位置、公式提示有无），"这个平台像好几个团队拼的"。
- **运维**：改一次交互规范要动几十上百个文件。

### 建议（P1）
沉淀一套**底稿专用组件库**（`components/workpaper/kit/`）：
- `<WpSection title objective guidance>`：统一"标题行 + 审计目标 el-alert + 编制提示 details + 右侧 AI/复核按钮"。
- `<WpAmountCell>` / `<WpFormulaCell>`：统一金额格式（走 displayPrefs）+ 公式列虚线 tooltip。
- `<WpOpinionCard>`：统一审计说明/结论卡片（内置 autosize minRows:5 + AI + 复核）。
- `<WpImportExport>`：统一"导入导出▾"dropdown。
- `<WpDynamicTable>`：统一 13px/紧凑/auto-calc-col/合计行/新增删除行/账龄动态列。

把"铁律"从**文字约定**升级为**编译期强制**：能用组件的地方，ESLint 禁止手写等价结构。

---

## 四、【高】巨型文件 + 极致碎片化并存，运维成本高

### 实测证据
| 层 | 现状 |
|----|------|
| 前端巨型 | `LedgerPenetration.vue` 3,706 行 / `TrialBalance.vue` 2,683 / `GtC1EntityControl.vue` 2,830 / `DisclosureEditor.vue` 2,166 |
| 后端巨型 | `_d1_import_export.py` 2,989 / `smart_import_engine.py` 2,788 / `consistency_gate.py` 2,141 / `event_handlers.py` 1,725 |
| 碎片化 | **715 个 router 文件 + 731 个 service 文件**，router_registry 手工维护 |
| composable 爆炸 | **1,439 个** 底稿 composables（useD2X/useD3X… 大量同构重复） |

这是典型的"两头极端"：核心几个文件过大（改动风险高、review 难），同时服务/composable 又碎成上千个（认知负担、重复逻辑、改一个通用行为要动 N 处）。

### 建议（P1，渐进）
1. **巨型文件拆分**（按域，不是按行数硬切）：`event_handlers.py` 按事件域分包；`consistency_gate.py` 抽规则表；`LedgerPenetration.vue`/`TrialBalance.vue` 抽子组件 + composable。设 CI size guard（已有 `test_wp_large_file_size_guard` 的模式，推广到 Top-20）。
2. **composable 工厂化**（memory 已提但未彻底落地）：`createCycleFormData`/`createDualMode`/`createImportExport`/`createDetailTable(agingConfig)` 参数化工厂，把 1,439 个收敛到"工厂 + 少量循环特化"。**每减少一类重复，就少一类"改A漏B"的 bug**。
3. **router/service 分域聚合**：按审计循环/领域建 package + `__init__` 聚合注册，减少 router_registry 手工维护面。

---

## 五、【高】数值/取数没有统一 SDK，各底稿"自己 fetch 自己拼"

### 实测证据
- 本次修 D2-1 试算表取数：发现要自己传 `year`、自己 `find(standard_account_code==='1122')`、自己兜底字段——**每个底稿都在重复这套易错逻辑**（漏 year 就 422，字段名猜错就取不到）。
- `useLedgerCache` 已有序时账缓存单例（好设计），但"审定数/未审数/科目余额/辅助余额"的取数没有同等收敛。

### 建议（P1）
建 `useAuditData(projectId, year)` 统一取数 hook / SDK：
- `getTbAmount(accountCode, {basis:'audited'|'unadjusted'})`、`getAging(subject)`、`getLedgerEntries(...)`、`getPrevYear(...)` 全部内置 year 解析、字段归一、缓存、错误降级。
- 底稿只调语义方法，不碰 URL/参数。**取数口径（借正贷负 v1 / 正数 v2 / 损益发生额）这类"铁律"内聚到一处**，杜绝各底稿口径漂移（memory 里已有多次口径漂移踩坑）。

---

## 六、【中高】四表-未审报表-审定表-底稿-调整分录-附注 联动：链路已建，但"可视化穿透"与"失效传播"待补齐

### 实测证据（正面）
- 链路是平台的核心资产且确实存在：ACNR addr_id 寻址、公式引擎 resolve_ref、调整分录增量重算、报表/附注回填、交付导出 flatten——设计完整。
- 已有 `LinkagePanoramaView.vue` / `ConsistencyDashboard.vue` / `ReportTracePanel.vue`。

### 待补
1. **穿透的"最后一公里"体感**：GtIndexChip 跳转已铺开，但从"报表某数"一路反查到"哪张底稿哪个单元格哪笔调整"的**一屏式追溯链路**还不统一（ReportTracePanel 与 底稿 chip 是两套入口）。
2. **失效传播的确定性**：draft-refresh/stale 曾有空壳，说明"改了上游、下游标脏、合伙人一键刷新"这条链的**端到端可靠性**需要一次全链路 Playwright 实测背书（不是单测绿就行）。

### 建议（P2）
- 统一"**溯源抽屉**"组件：任意金额右键 → 显示"四表→报表→审定→底稿→调整→附注"完整链 + 每一跳可点击跳转。收敛 ReportTracePanel 与 chip 两套。
- draft-refresh 做一次**五角色端到端演练**（合伙人点刷新 → 审计助理看到底稿初稿 → 经理复核 → 附注同步 → EQCR 抽查），Playwright 录制为回归。

---

## 七、【中】权限矩阵：有 store 有角色，但"判断散落 + 前端为主"

### 实测证据
- `roleContext.ts` 设计不错：systemRole + effectiveRole + 项目级 permission_level（edit/review），`canEditInProject`/`canReviewInProject` getter。
- 但 `canEditInProject` 只认 `'edit'`，各底稿仍自行判断 `isReadonly`；`usePermissionMatrix`/`BUILDER_ROLES` 等又是另一处判断。**同一个"谁能编辑"分散在多处**。
- 5 角色（助理/经理/业务合伙人/质控合伙人/EQCR）里，**质控与 EQCR 的"只读+批注+退回"权限边界**在前端是否被严格执行，需要统一收口。

### 建议（P2）
- 建**单一 PermissionMatrix 服务**（前后端共享定义）：`can(action, resource, context)` 一个入口。前端所有 `isReadonly`/按钮禁用/字段可编辑都走它。
- 后端 deps 层强制（已有 `require_wp_edit_permission` 雏形），前端只做体验优化不做安全边界——**安全判定必须后端兜底**（memory 已有此原则，需全面执行）。

---

## 八、【中】工程纪律：编码破坏、假绿、脚本改 Vue 反复踩坑

### 实测证据（全是真实教训）
- **PowerShell `Set-Content` 破坏 UTF-8 中文**：本会话就发生了（D2TabIndex 等被改乱码 → git checkout 恢复）。memory 里明文列为铁律，但**没有工程手段阻止**，靠人记。
- **"假绿"**：单测传真 ref 通过、Volar 无诊断，但浏览器 500/白屏（ref-unwrap、import 层级、模板内嵌引号）——反复出现。
- **相对导入层级 bug**：125 文件/244 处，靠脚本批修。

### 建议（P1，性价比极高）
1. **pre-commit 硬门禁**：①UTF-8/中文完整性检查（`raw.count(b'\xef\xbf\xbd')`）；②Vite transform 全树冒烟（curl `/src/...vue` 看 200/500，比 Volar 权威）；③ref 契约 guard（已有）；④import 深度 guard（已有）。全部挂 CI **阻断**，不再靠人肉。
2. **工具层面禁用危险操作**：约定"Vue 文件只能用结构化编辑工具改，禁止任何 shell 文本替换"——写进 CI（检测 vue 文件 diff 里出现 replacement char 即 fail）。
3. **新底稿必过 Playwright 冒烟**：加一个"底稿渲染冒烟"测试集（每个 wp_code 打开一次，断言 0 console error + 关键区块存在），纳入 CI。**这是根治"假绿"的唯一手段**。

---

## 九、【中】AI / LLM 辅助：能力点铺开，但"上下文供给"与"一致体验"参差

### 实测证据
- AI 辅助按钮铺得很广（每个说明/结论区都有 🤖），统一走 `POST /ai/generate-text`——架构好。
- 但**上下文供给质量不齐**：有的传了 sheet/rowCount/联动数（D2 分析程序传了周转率等），有的只传空 context；OCR 作为 AI context 只在 C 类/抽凭做了。
- vLLM（Qwen3.5-27B）单点，Phase3 才上对话流；B60 待 vLLM。

### 建议（P2）
- 统一 **`buildAiContext(wpCode, sheet)`** 工厂：自动附带该底稿的联动数据、审定数、账龄、异常项、源模板方法论——让 AI 生成质量从"通用套话"升级为"基于本底稿实际数据"。
- AI 输出统一走"生成→预览 diff→确认填入"三段式（部分已做，需全覆盖），避免 AI 直接覆盖用户已填内容。

---

## 十、其他值得全局考虑的点（简列）

| 维度 | 现状/建议 |
|------|-----------|
| **枚举/字典** | `dict.ts` store 存在；建议所有下拉（关联关系/交易类型/账龄/科目方向）走统一字典服务 + 支持项目级自定义（账龄已做，推广） |
| **年度** | year 参数反复手传易错（见第五点）；统一从 projectContext 注入 |
| **复制** | 序时账已有"复制选中"；底稿表格建议统一支持 Excel 粘贴/复制（大量录入场景刚需，审计助理高频） |
| **知识库/对话** | KnowledgeBase + ForumPage + ReviewConversations 三处交流入口，建议统一"项目内协作流"入口，避免割裂 |
| **附件/OCR** | RapidOCR 单机；行级 OCR 范式已统一（好）；建议附件与底稿单元格的"证据锚点"关系持久化，复核可一键看证据 |
| **工时** | WorkHoursPage 存在；建议与任务/底稿完成度联动（填底稿自动带出工时建议），减少二次录入 |
| **离线/协作** | 有 OfflineConflictWorkbench；6000 人并发目标下，需压测 SSE/EventBus 广播的扇出成本 |
| **查询** | 高级查询模块已完成（85/85）；建议把"高级查询"作为溯源/取数的统一后端，减少各底稿裸 SQL/裸 fetch |

---

## 十一、落地路线（建议排期）

**第一波（1-2 周，体感最强 + 止血）**
1. displayPrefs 收敛到 store + CI 守卫（第一点）
2. pre-commit 硬门禁：UTF-8 + Vite 冒烟 + ref/import guard（第八点）
3. 底稿渲染冒烟测试集（第八点）

**第二波（3-4 周，防漏 + 沉淀）**
4. `<GtWorkpaperShell>` 骨架 + 全局能力默认注入 + Coverage Ledger（第二点）
5. 底稿 UI Kit 组件库（第三点）
6. `useAuditData` 统一取数 SDK（第五点）

**第三波（持续，降本）**
7. composable 工厂化 + 巨型文件拆分 + router/service 分域（第四点）
8. 统一 PermissionMatrix（第七点）
9. 溯源抽屉 + draft-refresh 端到端演练（第六点）
10. AI 上下文工厂（第九点）

---

## 结语（合伙人视角）

这个平台的**功能深度**已经超过市面上多数商业审计软件——全循环底稿、四表全链联动、ACNR、公式库，这些是真功夫。现在到了一个关键拐点：**必须把"功能扩张期"沉淀下来的一次性约定，升级为工程化的强制机制**。

否则随着底稿/循环继续增加，"改 A 漏 B、新页面漏接全局、假绿上线"的成本会吞掉新功能的收益。上面十条里，**第一、二、八条是"投入小、对全体用户与运维即时受益"的止血项，强烈建议优先做**；其余是让平台"长期可维护、体验一致"的地基。

一句话总结给管理层：**"不要再加新循环了，先花一个月把全局机制焊死，之后每个新底稿的开发成本和 bug 率都会断崖式下降。"**
