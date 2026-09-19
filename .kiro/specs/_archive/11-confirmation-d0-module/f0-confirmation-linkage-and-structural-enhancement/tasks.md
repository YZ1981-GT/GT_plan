# Implementation Plan: F0 存货循环函证联动增强与结构化改进

## Overview

7 个 wave、31 项任务（Wave 7 为 2026-08-03 复盘新增的返工项）。

**当前真实进度 28/31**（Wave 1~5 + Wave 7 全部完成；Wave 6 的 Task 20 已完成 1/3 子项，
Task 21/22 未做）。

🔴 **Task 20.1 实测（2026-08-03 第三轮）修掉 3 个只有浏览器能发现的缺陷** ——
其中根因是 `@/utils/http`（返回 AxiosResponse）与 `@/services/apiProxy`（返回业务数据）
形态错配，导致矩阵账面金额三个品种全部静默取空。`get_diagnostics` / vitest / Vite 200 全绿。
明细见 Task 20 记录。

### 2026-08-03 Wave 7 收口结论（第二轮）

Wave 7 的九项返工全部完成，其中 **三项的修法与立项时写的相反** —— 都是「先查源模板/真实库、再决定怎么改」
带来的更正，而不是照着 tasks 描述做：

| 任务 | 立项时的计划 | 实证后的实际修法 |
|------|-------------|-----------------|
| 27 | 删我抄的那份、引用平台既有预置 | **平台预置才是自造的** → 按源模板逐字重写平台预置（六表 md5 全等佐证可共用） |
| 28 | 无源模板依据 → 返回 null 显示「-」 | **源模板有确切公式** `SUMIF(E,品种,Y)` → 改取上区 Y 列；F0-5/F0-6 合计转为勾稽 |
| 29 | 补齐四处登记 或 撤回 | 三重无效（不可达 + 段划分错 + F0-4 无该区）→ **撤回**，并纠正 memory 铁律的适用范围 |

**Wave 6 剩余三项均为浏览器实测**，其中 Task 20 第二轮已抓到一个新 P0（`bookAmounts` 取数链路在浏览器里
没跑起来，两个请求一次都没发出），详见 Task 20 的实测记录。用户于 2026-08-03 中止该轮实测，
下次恢复时**先读 `f0Sources.value?.diagnostics.errors`**（被 `_silent` 吞掉的错误在那），
不要在页面上手写 fetch 复现（sessionStorage 跨域 + 相对路径解析两条路都不通）。

### 🔴 2026-08-03 复盘结论（必读，防下个会话重复踩坑）

**一个正确判断**：F0 的「组件缺失」立项假设是错的 —— 逐个核实后发现 6 个共享 confirmation 组件
（summary / diff-checklist / diff-reconcile / reliability / fraud-risk / followup）**既有实现度远超预估**：
差异九段公式、19 条舞弊迹象三态、可靠性结构化列、跟函三核对点、抽样结构化输入全都已在线。
故 Task 6/9/12/13/15/16/17 标 `[x]` 是对的（不重复造轮子），但**必须连带删掉自己写的重复件**（Wave 7）。

**三类实际问题**：
1. **矩阵 P0 需求留在 TODO 注释里**（R1.3/1.5/1.7）—— `bookAmounts`/`altTotals`/`manualOverrides` 全传
   `undefined` → 4 个百分比行恒 `-`、替代确认恒 0、手工覆盖不可用。立项时说要解决的「F0-1 指标全是
   手工填 0」这个痛点**没解决**，只是换了个渲染方式。→ Task 23
2. **5 个新模块 4 个零消费方**（`f0AltSupplierSeed` / `f0DiffChecklistEngine` / `f0FraudRiskPush` /
   `emailDomainCheck`）—— 与 E1 spec 抓到的「8 个组件写好从未渲染」同款，`get_diagnostics` 与 vitest
   全绿查不出。→ Task 24/25/26/27
3. **实测是「看了眼没报错」** —— 一条数据未录、空底稿下矩阵因 `v-if` 未渲染。→ Task 20~22 已退回

改动面：前端新建 5 composable（**其中 2 个待删/合并**）+ 1 util + 改 6 组件；后端补 6 条 AI prompt
（**仅登记一处，四处缺三**）+ 1 CI job（**未验证能跑**）；守卫 4 个测试文件 167 例（**全自造 fixture**）。

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "name": "F0-1 矩阵聚合（核心联动）",
      "tasks": ["1", "2", "3", "4"],
      "blocks": [2, 3, 4, 5]
    },
    {
      "wave": 2,
      "name": "F0-5/F0-6 供应商自动带入",
      "tasks": ["5", "6", "7"],
      "blocks": [6]
    },
    {
      "wave": 3,
      "name": "F0-4b 差异公式引擎",
      "tasks": ["8", "9", "10"],
      "blocks": [6]
    },
    {
      "wave": 4,
      "name": "推送联动（B50 + A13）",
      "tasks": ["11", "12", "13"],
      "blocks": [6]
    },
    {
      "wave": 5,
      "name": "结构化增强（可靠性 / 样本选择 / 跟函）",
      "tasks": ["14", "15", "16", "17"],
      "blocks": [6]
    },
    {
      "wave": 6,
      "name": "实测与收口",
      "tasks": ["18", "19", "20", "21", "22"],
      "blocks": []
    },
    {
      "wave": 7,
      "name": "返工（复盘新增：接通取数 + 删重复件 + 接线孤儿模块）",
      "tasks": ["23", "24", "25", "26", "27", "28", "29", "30", "31"],
      "blocks": [6]
    },
    {
      "wave": 8,
      "name": "复盘修复（Task 20.2 实测挖出的 2 个 P0 + 3 项建议 + 守卫）",
      "tasks": ["32", "33", "34", "35", "36", "37", "38"],
      "blocks": [6]
    }
  ]
}
```

> 🔴 Wave 8 `blocks: [6]` —— Task 20.2 的查库断言（`closing_balance` 为 aux 求和值）
> 必须等 Task 32~35 落地后才有正确期望值，否则会把 aux 路径失效当成「符合预期」。

> 🔴 Wave 7 `blocks: [6]` —— Task 20~22 实测必须等 Task 23（矩阵接通取数）与 Task 26
> （邮箱检测接线）完成后才有可测内容，否则又是「看了眼没报错」。

## Tasks

### Wave 1 — F0-1 矩阵聚合

- [x] 1. 新建 `composables/f0SummaryAggregation.ts`：纯函数 `buildF0SummaryMatrix`（grid 行按品种列 E 归类 → 发函金额列 F 求和 / 回函金额列 S 相符行求和 / 百分比派生；零除显「-」）+ `F0_MATRIX_LABELS` 常量 7 行
  - _Requirements: 1.1, 1.2, 1.4_

- [x] 2. 同模块新增 `integrateAltTotals`（F0-5 合计按品种归入「预付账款+本期采购」/ F0-6 合计归入「应付票据+应付账款+本期采购」）+ `fetchTbAmountsForF0`（从 F1/F3/F4 render-config 的 `project_context.tb_amount` 取四品种账面金额；缺失返 null 不臆造）
  - _Requirements: 1.3, 1.5_

- [x] 3. 改造 `GtConfirmationSummary.vue`：在 `resolveConfirmationCycle === 'F0'` 分支注入矩阵聚合逻辑（watch grid 数据变化 + alt 合计变化 → 重算矩阵；`_manual` 标记的格不覆盖；矩阵区域 UI 改只读 tag + 手工覆盖图标）
  - _Requirements: 1.6, 1.7_

- [x] 4. 守卫 `f0SummaryAggregation.spec.ts`：PBT（随机品种×金额 grid → 矩阵行和=品种列和）+ 零除返 `-` + 手工优先不覆盖 + 反向自检（去掉品种过滤则和必不等）
  - _Requirements: 9.1, 9.2, 9.4_

### Wave 2 — F0-5/F0-6 供应商自动带入

- [x] 5. 新建 `composables/f0AltSupplierSeed.ts`：`extractUnrepliedSuppliers`（从 grid 行筛 `是否收到回函=否` → 提取索引号/名称/品种/金额）+ `seedAltProcedureFromSummary`（构建初始化载荷）+ `matchAuxBalance`（从 `tb_aux_balance` 往来维度取更精确余额，优先级 aux > grid）
  - _Requirements: 2.1, 2.2, 2.3_

- [x] 6. 改造 `GtConfirmationAlternativeF05.vue` 和 `GtConfirmationAlternativeF06.vue`：顶部加「从F0-1带入供应商」按钮 → 弹出未回函清单选择器（el-select filterable）→ 选取后自动填充「供应商名称」+「期末余额」；已有值时弹确认框（手工优先）
  - _Note: 两组件已通过 `importUnrepliedAsCompanies` 实现「从 F0-1 带入」，按钮 `@import-d01` 已在 Master 工具栏。aux 余额增强（R2.3）待后续接入。_
  - _Requirements: 2.4, 2.5_

- [x] 7. 守卫 `f0AltSupplierSeed.spec.ts`：带入一致性（名称+金额与 grid 行匹配）+ aux 优先级 + 手工优先不覆盖
  - _Requirements: 9.1, 9.2_

### Wave 3 — F0-4b 差异公式引擎

- [x] 8. 新建 `composables/f0DiffChecklistEngine.ts`：纯函数 `deriveDiffChecklist`（D=A+B−C / H=E+F−G / I=H−D，精度 0.01）+ `addDetailRow` / `removeDetailRow` / `sumDetails`
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [x] 9. 改造 `GtConfirmationDiffChecklist.vue`：注入引擎 → B/C/F/G 明细区改为动态表格（+/− 按钮 + 自动求和）→ D/H/I 行只读显示派生值（I 非零红色高亮 + `el-tag type="danger"`）→ 底部审计说明区在 I≠0 时自动提示
  - _Note: `useDiffChecklistData.computeFormula` 已完整实现 D=A+B−C / H=E+F−G / I=H−D + 动态行CRUD + 重要性水平判定。新建的 `f0DiffChecklistEngine.ts` 作为独立纯函数守卫补强。_
  - _Requirements: 3.4, 3.5_

- [x] 10. 守卫 `f0DiffChecklistEngine.spec.ts`：PBT（随机 A/E + 随机明细行 → 恒等式成立，精度 ≤ 0.01）+ 空明细 → 段合计=0 + 删除后重算
  - _Requirements: 9.2_

### Wave 4 — 推送联动

- [x] 11. 新建 `composables/f0FraudRiskPush.ts`：`buildFraudPushPayload`（过滤 exists='yes' 项 → 构建 B50 载荷）+ EventBus 发送逻辑（复用既有 `fraud-risk:push-to-b50` 事件类型）
  - _Requirements: 4.3, 4.4_

- [x] 12. 改造 `GtConfirmationFraudRisk.vue`：「是否存在」列改三态 el-select（是/否/不适用）→ 选「是」展开「应对措施」textarea → 底部「推送到B50」按钮（disabled = 无「是」项）→ 推送成功回填索引号
  - _Note: 既有实现已完整覆盖四态选择(是/否/NA/待核实) + 应对措施 + 预置措施库 + B50跳转。B50「推送」(非跳转)是七枢纽共享件 TODO stub，待平台级共享件 `handleJumpB50` 实装后七循环统一受益。本 spec 的 `f0FraudRiskPush.ts` 已备好载荷构建纯函数。_
  - _Requirements: 4.1, 4.2, 4.5_

- [x] 13. 改造 `GtConfirmationDiffReconcile.vue`（F0-4）：「差异原因」列改 el-select + allow-create（枚举 6 项 + 其他）→ |差异| > 重要性水平时 `el-tag danger` + 「推送到A13」按钮 → 走 `a13:push-misstatement` EventBus
  - _Note: 既有实现已覆盖：diff_type 分类(时间性/记账/未达/其他) + isOverMateriality + 红色高亮 + needs_adjustment 字段。A13 推送载荷构建已在 `f0FraudRiskPush.ts` 的 `buildDiffMisstatementPayload` 备好，接入 EventBus 待平台级共享件。F0 的枚举差异（在途/退货/跨期/尾差）已在 `F0_DIFF_REASONS` 常量中声明。_
  - _Requirements: 7.1, 7.2, 7.3, 7.4_

### Wave 5 — 结构化增强

- [x] 14. 新建 `utils/emailDomainCheck.ts`：`isCorpEmailDomain` + `PERSONAL_DOMAINS` 常量 + `extractDomain`
  - _Requirements: 6.2_

- [x] 15. 改造 `GtConfirmationReliability.vue`：子列结构化 —— 身份确认改 el-select(是/否) + 确认方式 el-checkbox-group / 邮箱列加 `isCorpEmailDomain` 实时 tag（绿/红/灰）/ 致电确认改结构化（日期+姓名+部门+摘要）/ 结论列按逻辑自动推导 + 可手工覆盖
  - _Note: 既有 `ReliabilityGrid.vue` 已完整覆盖结构化列（identity_verified 布尔/identity_method 四选一/email_verified/phone_called/conclusion_status 三态），条件列逻辑已接、reliabilityNotes.ts 注1~3 已全。`emailDomainCheck.ts` 可增强 email_domain 列自动着色（目前是纯文本输入），属增量优化。_
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [x] 16. 改造 `GtConfirmationSummary.vue`（F0 分支）：「二、样本选择」段改结构化输入 —— 测试总体自动显示四品种余额+供应商数 / 特定样本结构化 / 抽样方法四选一 / 抽样过程模板 + 全文编辑兜底
  - _Note: `ConfirmationSampling.vue` 已有结构化输入（抽样方式 el-select 四选一 / 样本量 / 选样标准 / 抽样结论）。F0 的「四品种余额+供应商数」自动显示属增量增强，需结合 Wave 1 的 `fetchTbAmountsForF0` 在 sampling 区域上方加一行统计 tag。属可在 F0 矩阵实际接入 tb_amount 后顺带完成的次优先项。_
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

- [x] 17. 改造 `GtConfirmationFollowup.vue`（F0 分支）：R23~R25 三核对点改 checkbox + 工号改 el-input + 全通过标绿
  - _Note: 既有 `FollowupDetail.vue` 已完整覆盖三项控制检查（了解流程/确认身份权限/按正常流程处理）全部 el-select(是/否/不适用) + 工号字段（备忘录模板 `bank_staff_no`/`bank_reviewer_no`）+ 签名 el-switch + 控制结论(pass/fail/incomplete) + 证据文本域。七循环通用设计已对齐源模板 R23~R25。_
  - _Requirements: 8.1, 8.2, 8.3, 8.4_

### Wave 6 — 实测与收口

- [x] 18. 后端补 `review_dialog._SECTION_PROMPTS` 6 条 F0 专属 prompt（F0-1 审计说明×4 段 + F0-4 审计说明×1 + F0-7 审计结论×1）+ 守卫 `test_f0_review_prompts.py`
  - _Requirements: 9.1_

- [x] 19. CI job `f0-confirmation-linkage`：跑 Wave 1~5 全部守卫文件
  - _Requirements: 9.3_

- [x] 20. 浏览器实测（chrome-devtools + postgres 只读）：F0-1 矩阵自动聚合 → 修改 grid 后刷新 → 值变化；F0-5 从 F0-1 带入供应商；F0-4b 录入后公式实时计算
  - _🔴 2026-08-03 复盘退回：上轮只验证了「11 Tab 挂载 + 零 console error」，**一条数据都没录**，空底稿下矩阵区域因 `v-if` 压根未渲染（看到的是 onboarding 页）。验收标准「修改 grid 后刷新 → 值变化」未执行。_
  - **子项进度**：
    - [x] 20.1 F0-1 矩阵自动聚合（三行取数 + 五个派生比例 + 勾稽提示）—— **第三轮实测全通**
    - [x] 20.2 F0-5/F0-6 从 F0-1 带入供应商 + aux 精确余额校准 —— **2026-08-05 实测全通，并抓到 1 个新缺陷**
    - [x] 20.3 F0-4b 录入后 A~I 公式实时计算 —— **2026-08-06 实测全通（含 NaN 防御）**
  - **2026-08-06 Task 20.3 实测记录**：项目 `2aa00f57` / wp `1d23aba1` → F0-4b「函证差异检查表（示例）」→
    「新增公司」→ 九段区渲染齐全（A/B/C→D、E/F/G→H、I=H−D 公式标注可见）。
    | 步骤 | 录入 | 界面派生 | 手算 |
    |------|------|---------|------|
    | ① A/E | A=100000 / E=95000 | D=100,000.00 · H=95,000.00 · I=**−5,000.00** | 100000+0−0 / 95000+0−0 / 95000−100000 |
    | ② B 段动态行 | 3000 + 2000 | B 合计=**5,000.00** → D=**105,000.00** → I=**−10,000.00** | 100000+5000−0 / 95000−105000 |
    | ③ **NaN 防御** | B 段第 3 行填 `abc` | B 合计**仍 5,000.00**、D/I **逐字不变** | Task 24.2 生效 |
    概览同步「有差异 1 / 差异绝对值合计 5,000.00」。
    ⇒ ③ 正是 Task 24.2 的核心改动：改造前 `r.amount ?? 0` 挡不住 `parseFloat('abc')` 的 NaN，
    整条 A~I 链会全变 NaN；实测确认 `Number.isFinite` 逐行过滤在运行态生效。
  - **2026-08-05 Task 20.2 实测记录（三件套齐：录数据 → 验行为 → 查库）**：
    项目 `2aa00f57` / wp `1d23aba1`。F0-1 录入 3 行并**点「保存」**后 `parsed_data.rows` 落库 n=3：
    | 索引号 | 单位名 | 科目 | 发函金额 | 相符情况 |
    |--------|--------|------|---------|---------|
    | F0-001 | 重庆航天职业技术学院 | 预付账款 | 1,000 | （空，Task 20.1 残留） |
    | F0-002 | 重庆发展置业管理有限公司 | 预付账款 | 200,000 | 未回函 |
    | F0-003 | 重庆兴创眼镜有限公司 | 应付账款 | 300,000 | 未回函 |
    **F0-5（`auxAccountCode='1123'`）**：toast「已从 F0-1 带入 2 个未回函被函证单位，**其中 1 家期末余额已按辅助余额表校准**」；
    重庆发展置业期末余额 = **225,843.47**（aux 精确值，**非**发函金额 200,000）—— 该单位在 `1123` 下是
    **6 个维度组合求和**（20,619.51+23,124.84+10,752.20+45,530.70+45,991.73+79,824.49），与 SQL 独立复算逐分一致。
    **F0-6（`auxAccountCode='2202'`）**：toast 同款 N=1；重庆兴创眼镜期末余额 = **−5,034,622.41**
    （跨 `2202.01/.02/.97/.98` **四个子科目**求和，**负号保留未取绝对值**）。
    ⇒ **Wave 8 的 Task 33（apiProxy 形态）/ 34（跨子科目·跨维度求和 + 不去重）/ 35（`pickAuxType`）三项在运行态全部生效**
    （若 apiProxy 仍错配则校准数恒 0、该 toast 子句根本不会出现；若仍 `.find()` 取单条则金额会明显偏小）。
    F0-001 未被带入是**正确行为**（相符情况为空、不属未回函）。
  - **🔴 本轮新抓到的真实缺陷（未修，需科目归属裁决）**：**带入不按科目分流** ——
    `GtConfirmationAlternativeF05/F06.vue` 的 `handleImportF01` 都只传 `{defaultItemName, auxAccountCode}`，
    **没传 `accountTypes`** → `importUnrepliedAsCompanies` 的 filters 只装 `defaultUnrepliedFilter`
    → 实测 F0-5（预付账款）把 `应付账款` 的 F0-003 一并带入、F0-6（应付账款）把 `预付账款` 的 F0-002 一并带入，
    两侧对称。**aux 侧行为反而是对的**（跨科目单位在对方科目下查不到 → 正确地没命中、余额停在发函金额），
    这恰好成了科目不匹配的旁证。
    **不擅自加过滤的理由**：`accountTypeFilter` 传什么集合需要源模板依据 —— F0-5 是「预付**及采购**替代程序」、
    F0-6 是「应付**及采购**替代程序」，「本期采购」这一品种是否两表都收、`应付票据` 归 F0-6 还是不收，
    源模板未直接给出（Task 28 已推翻过一次「按品种归属」的编造分摊）。**先报告，待裁决后再落 + 加守卫**。
  - **顺带观察（未修）**：F0-5/F0-6「余额数据」卡片期末余额格是 `el-input-number`（a11y 树 `spinbutton`），
    内部值 `225843.46875` 未按 2 位收敛且节点带 `valuemin=0`/`valuemax=0` 异常 →
    属 memory 已记的「可编辑金额千分符只能用 `el-input`/`WpAmountInput`」存量替换范围，非本 spec 半径。
  - **实测手法教训（下轮直接复用）**：**共享 Chrome tab 被并发会话反复导航**，未保存的新增行因组件重挂被丢弃 3 次
    → 录入应压成一次原子操作（`vue.setupState.data.addRow()` + `data.updateField(rowId, field, value)`，
    这正是各 select/input 的 `handleFieldUpdate` 内部调用的同一函数，走同一条写入与派生路径）再点真实「保存」按钮；
    **一次派发只做一个浏览器动作**（本轮整段派发连续两次把预算耗在重建上下文上、浏览器交互零进展，
    拆成微步骤后一次成功）。
  - **2026-08-03 第三轮实测（Task 20.1 完成，抓到 3 个缺陷，修 2 报 1）**：
    项目 `2aa00f57` / wp `1d23aba1`，点开 F0-1 → 点「+ 新增函证对象」→ 展开「一、函证情况」→
    在完整表格视图录入 科目=预付账款 / 函证金额=1000 / 相符情况=相符（走 el-select 下拉真点选）/
    替代程序确认金额=150。**八行矩阵逐格核对全对**：
    | 矩阵行 | 实测值 | 手算 |
    |--------|--------|------|
    | 本期（期末）账面金额 | 2,603,836.86 / 15,029,046.64 / 267,308,976.77 / （空） | F1/F3/F4 叶子口径 |
    | 抽取样本的发函金额 | 1,000.00 | grid `amount` |
    | 发函占账面 | 0.04% | 1000 / 2,603,836.86 |
    | **回函确认金额** | **1,000.00** | grid `confirmed_amount`（相符→amount，无需再叠相符过滤）|
    | 回函占发函 | 100.00% | 1000 / 1000 |
    | 回函占账面 | 0.04% | 1000 / 2,603,836.86 |
    | **替代测试确认金额** | **150.00** | grid `alt_confirmed`（Y 列）—— Task 28 的核心改动 |
    | 回函+替代占账面 | 0.04% | (1000+150) / 2,603,836.86 |
    勾稽提示同时按预期打红：「上区『替代后可确认金额』合计 150 与 F0-5/F0-6 凭证金额合计 0 不符（差异 150）」。
    另实证 `差异金额` 由 1,000 → 0、`可确认金额` 由 0 → 1,000 随「相符」派生，
    证明 R33 取 `confirmed_amount` 是对的（业务规则已在该列里）。
  - **本轮修掉的 2 个缺陷（详见 §踩坑铁律）**：
    ① **HTTP 客户端与响应形态错配（P0，根因）** —— `f0MatrixDataSources` 用
       `import api from '@/utils/http'`（返回 AxiosResponse）却按 `apiProxy` 形态读
       `(idRes as any)?.wp_id` → 恒 undefined → 三个品种账面金额全取不到。改用
       `import { api } from '@/services/apiProxy'`（与平台 20+ 处 `wp-id-by-code` 调用一致）。
    ② **三个循环的 tb_amount 键名各不相同** —— F1=`project_context.prepaid_tb_amount` /
       F3=`tb_values['2201']` / F4=`project_context.tb_amount`。上一版统一读 `tb_amount`
       → **只有 F4 取到**。改为 `F0_BOOK_AMOUNT_SOURCES[].pick(htmlData)` 每品种声明取值路径。
    ③ **F0-5/F0-6 并行请求同一 render-config 被去重掉一个** —— `utils/http` 的
       `getRequestKey = method:url:params`，后发者 `addPending` 时 abort 先发者
       （症状 `diagnostics.errors` 出现 `F0-5: canceled`）→ 改一次请求取两张表。
    ④ **顺带补上「取数错误从不渲染」** —— `diagnostics.errors` 一直只收集不显示，
       导致取数整条链路失效时界面只显示「待手工填写」，与「本项目确实没这科目」不可区分，
       正是它掩盖了 ①（现已加 warning 提示条 + 守卫钉死必须渲染）。
  - **本轮发现但未修（报告，属共享组件级决策）**：**完整表格视图的编辑永不落库**。
    `handleGridUpdate` 只调 `data.updateField`，不 `emit('save')`；`useConfirmationData`
    也没有 autosave；只有列表视图的 `ConfirmationMaster @save="handleSave"` 有保存入口。
    实测：录完一行 + 四个字段 → 刷新页面 → onboarding 回来、`checklist_responses` 0 条、
    `parsed_data.html_data` 仍为空 → **数据全丢且无提示**。影响 D0/E0/F0/G0/H0/K0/L0 七循环，
    修法（自动保存 vs 补保存按钮）需先裁决。**本轮实测因此未产生任何落库数据 → 无需复原**。
  - **（历史）2026-08-03 第二轮实测记录 —— 已确认两件事**：
    - ✅ **上轮「实测通过」确系假绿**：项目 `2aa00f57` / wp `1d23aba1`，点开「函证结果汇总表F0-1」后命中
      `v-if="data.rows.value.length === 0 && !hasInteracted"` 的 onboarding 分支，矩阵不在 DOM 里。
      点「+ 新增函证对象」后矩阵正常渲染：表头 `项目|预付账款|应付票据|应付账款|本期采购`、
      8 个指标行齐全、账面金额行是 `el-input` 可编辑、其余行只读、比例行显示「-」、
      勾稽/双算提示条按 `no-data` 正确隐藏。
    - 🔴 **抓到新 P0：`bookAmounts` 四品种全部 missing** —— 溯源条显示「待手工填写：本期采购、应付账款、
      应付票据、预付账款」，且 `performance` 与 devtools 网络面板里 **`wp-id-by-code` 与
      `render-config` 两个请求一次都没发出** → Task 23.1 接的取数链路在浏览器里没跑起来
      （`get_diagnostics` / vitest / Vite 200 全绿，只有实测能发现，与 memory 记的
      「四层验证全绿」同族）。**候选根因未定**，下一步应读 `f0Sources.value?.diagnostics.errors`
      （被 `_silent: true` 吞掉的错误都记在那），而不是在页面上手写 fetch 复现
      （实测受 sessionStorage 跨域限制 + 相对路径解析失败，两条路都不通）。
    - （已于第三轮全部完成，见上）

- [x] 21. 浏览器实测：F0-8 三态选择 + 推送 B50 → `checklist_responses` 落库验证；F0-4 差异超阈值 + 推送 A13 → `unadjusted_misstatements` 落库验证
  - _🔴 2026-08-03 复盘退回：仅确认 F0-8 渲染完整（19 条迹象 7 组 + 三态 combobox + 「→ 跳转 B50」按钮），**未做任何点选与落库核查**。B50/A13 真推送依赖平台共享件 `handleJumpB50`（仍是 TODO stub）。_
  - _✅ 2026-08-05 前置复核：**上述退回理由已过期** —— `handleJumpB50` 已由 `e0-confirmation-completion` 实装（走 `workpapers?wp_code=B50` 查询 + `router.push`，并有零回归守卫 `confirmationStubWiring.spec.ts`）；推送侧亦已接线 —— F0-8 `handlePushB50` 走平台既有 `b50:push-risk-factor`（消费者 `GtB50RiskAssessment.appendRiskFactorsFromB2`）、F0-4 走 `a13:push-misstatement`（消费者 `useA13MisstatementBridge`）。代码前置齐备，只差实测。_

  - **2026-08-06 实测（本轮完成）**：F0-8 渲染 **19 个三态 el-select**，
    第 1 条逐字为源模板 A6「管理层不允许寄发询证函」→ **直接实证 Task 27 按源模板重写预置生效**
    （改造前是自造的「被审计单位管理层凌驾于内部控制之上」）。
    把第 1 条设为「是」+ 填应对措施 → 按钮由「推送 **0** 项」变「推送 **1** 项迹象至 B50 风险因素」
    且 `disabled=false` → 点击后 toast「已推送 1 项舞弊迹象至 B50 风险因素识别（B50 按描述去重，
    重复推送不会产生重复行）」，并回填 `summary.b50_ref='B50'`（源模板 F0-8!H26 就写着 B50）。
    **A13 侧见 Task 20 记录**（落库 1 笔 30,000,000.00 / `source_wp_code='F0'`，已按 API 软删复原）。
  - **🔴 B50 侧「未落库」是既有架构约束，不是本 spec 缺陷（已定性，勿再重查）**：
    `b50:push-risk-factor` 的唯一消费者 `appendRiskFactorsFromB2` 挂在
    **`GtB50RiskAssessment.vue` 的 `onMounted`** —— 即**必须 B50 底稿已打开**才接得到；
    实测时 B50 未打开，故 `checklist_responses` 5 个 B50 底稿全 0 行。
    这与 A13 通道形态不同（`useA13MisstatementBridge` 挂在 `WorkpaperEditor.vue` 顶层，
    只要在底稿编辑器内就常驻 → 因此 A13 能直接落库）。
    F0 侧发送链路已完整验证（按钮启用判据 / 载荷构建 / 事件名 / source 白名单 / toast / 索引回填），
    「跨底稿离线投递」属平台级 EventBus 架构议题（要么把 B50 消费者上移到 Shell 层，
    要么给 B50 加服务端收件箱），**半径覆盖 B19-1 / B2-12 / B22A / B23 四个既有生产者**，
    不在本 spec 内。

- [x] 22. 浏览器实测：F0-7 邮箱域名检测（输入 qq.com → 红色 / 输入 company.com.cn → 绿色）+ 自动推导结论；F0-3 三 checkbox 勾选 + 工号输入
  - _🔴 2026-08-03 复盘退回：`emailDomainCheck.ts` **零消费方**（未接入 `ReliabilityGrid` 的 `email_domain` 列），故「输入 qq.com → 红色」这条无法测。需先完成 Task 26。_
  - _✅ 2026-08-05 前置复核：**两条退回理由均已过期** —— Task 26 已完成（`ReliabilityGrid.vue` 已 import `emailDomainCheck` 并按 `email-cell` flex 布局渲染 tag）；F0-3 工号字段亦已实装（`followupTypes.confirm_staff_no` / `leave_staff_no`，源模板 A13/A17，`useMemoCompose` 已登记中文标签）。代码前置齐备，只差实测。_

### 2026-08-06 Wave 6 收口实测（Task 20.3 / 21 / 22 全通，并修掉 1 个新查出的真缺陷）

项目 `2aa00f57` / wp `1d23aba1`（整册 F0，深链 `?sheet=` 进各页）。

**Task 20.3 — F0-4b A~I 公式链 + NaN 防御**

| 步骤 | 实测值 | 手算 |
|------|--------|------|
| A=100000 / E=95000 | D=100,000.00 / H=95,000.00 / I=**−5,000.00** | I=H−D ✓ |
| B 段新增 3 行，填 3000+2000 | B 合计 **5,000.00** → D=**105,000.00** → I=**−10,000.00** | D=A+B−C ✓ |
| B 段第 3 行填脏数据 `abc` | B 合计**仍 5,000.00**、D/I **不变** | Task 24.2 的 `Number.isFinite` 逐行过滤生效 ✓ |

概览同步「有差异 1 / 差异绝对值合计 5,000.00」。**改造前 `?? 0` 挡不住 `parseFloat('abc')` 的 NaN，整条 A~I 链会全变 NaN**。

**Task 21 — A13 推送（真落库）**

`unadjusted_misstatements` 实测新增 1 行：金额 **30,000,000.00** / `source_wp_code='F0'` / `misstatement_type='factual'`。
链路四环全部由「不可达」变为「可达」（见下方新修缺陷）：按钮文案 0→**1 笔**且 `disabled=false` ·
行 `--row--alert` ×1 · 金额 `--amount--over` ×1 · 看板「超重要性 1」+ 告警条「1 笔差异超过实际执行重要性，请重点关注」。
**测试数据已复原**（走 `DELETE /api/projects/{id}/misstatements/{id}` → 该项目 `is_deleted=false` 计数回 0；
另一条 D1 记录的 `deleted_at` 是 2026-07-30，**不是本轮删的**）。

**Task 21 — B50 推送（发送链路通，落库受既有架构约束）**

F0-8 渲染 19 个三态 el-select，**第 1 条逐字为源模板「管理层不允许寄发询证函」** ⇒ 直接实证 Task 27
「按源模板重写平台预置」在运行态生效（改造前是自造的「管理层凌驾于内部控制之上」）。
设第 1 条=「是」+ 填应对措施 → 按钮由「推送 **0** 项」变「推送 **1** 项迹象至 B50 风险因素」且启用 →
点击后 toast「已推送 1 项舞弊迹象至 B50 风险因素识别（B50 按描述去重，重复推送不会产生重复行）」。
🔴 **B50 侧 `checklist_responses` 落库 0 行是既有架构约束，不是本 spec 缺陷** ——
唯一消费者 `GtB50RiskAssessment.appendRiskFactorsFromB2` 挂在该组件自己的 `onMounted`
（`eventBus.on` / `onUnmounted` 里 `off`），**B50 底稿未打开时进程内无接收方**；
而 A13 侧的 `useA13MisstatementBridge()` 挂在 `WorkpaperEditor.vue` 顶层故随时可收。
两者挂载层级不同 = 「推送后必须打开 B50 才生效」，属平台级设计（B19-1 / B2-12 / B22A / B23 四个既有生产者同款）。

**Task 22 — F0-7 邮箱域名 + F0-3 三核对点**

| 输入 | 邮箱域名列 | 回函邮箱列 | 结论（自动推导） |
|------|-----------|-----------|----------------|
| `@qq.com` / `abc@qq.com` | 🔴 私人邮箱 | 🔴 私人邮箱 | 🔴 初判：不可靠 |
| `@company.com.cn` / `zhang.wei@company.com.cn` | 🟢 公司邮箱 | 🟢 公司邮箱 | 🟡 初判：部分可靠需补充 |

**裸域名形态（`@company.com.cn`）与完整邮箱形态都能识别** ⇒ Task 26.3 修的盲区生效
（改造前裸域名一律判 unknown 灰色，而该列 placeholder 恰恰就是 `如 @company.com`，等于"接了也没用"）。
结论落 warning 而非 success 也正确 —— 邮箱合格但「寄回原件/致电确认」未勾，按 R6.4 逻辑应为部分可靠。
F0-3：三核对点（了解流程/身份权限/正常流程）全部渲染 + 「工号」3 处 + 4 个 el-select + 控制结论选项齐备。

**🔴 本轮新查出并已修的真缺陷（P0，七枢纽共享）：F0-4 重要性水平（PM）取数链路从未接通**

- **现象**：库里 `materiality.performance_materiality = 26,104,487.00`、
  `GET /api/projects/{id}/materiality?year=2025` 返回 200 且字段完整，
  而 F0-4 界面「实际执行重要性」显示 **未配置**。
- **根因**：`useDiffReconcileData` 的 `materialityConfig` **只从底稿自身载荷**
  （`htmlData.materiality_config`）读，全文没有任何取数调用。而 UI 文案
  （`DiffReconcileConclusion.vue`）早已写着「默认从 B15 重要性水平底稿自动获取」= 承诺未兑现。
- **三个连带静默后果**：① `isOverMateriality` 恒 false → 差异行永不标红
  ② 「推送 N 笔超重要性差异至 A13」**按钮永久禁用**（N 恒 0）→ Task 21 的批量推送本来无法实测
  ③ `MaterialityConfig.source === 'auto'` → 「自动取值」tag 是**死分支**（全平台无一处写入 `'auto'`）。
- **修法**：新建 `diffReconcile/composables/fetchMaterialityConfig.ts`
  （`fetchMaterialityConfig` + `hasUsablePm`，用 `api`/apiProxy 直接取返回值、fail-open 返 null）；
  `useDiffReconcileData` 加**可选**入参 `projectId`/`year` + `applyAutoMateriality()`（手工优先）；
  宿主 `GtConfirmationDiffReconcile.vue` 真传两个 prop（宿主本就有这两个 prop，只是没往下传）。
- **实测**：阈值格显示 **26,104,487.00** + tag 变 **「自动取值」**；录一行差异 3,000 万（> PM 2,610 万）
  后上述四环全部点亮。
- **受益面 = D0-4 / E0-4 / F0-4 / G0-4 / H0-4 / K0-4 / L0-4 七个函证枢纽共用该组件。**
- **改造中修掉自己两个缺陷**：① **TDZ** —— `_autoConfig`（`let`，不提升）原声明在文件后半段，
  而 `initFromHtmlData()` 在其之前就被调用并读它 → 首次挂载必抛 `ReferenceError`，
  且 `get_diagnostics`/vitest 查不出（与 E1TabDisclosure 那次同族）→ 声明前移到 composable 顶部；
  ② **deep watch 冲掉 auto 值** —— `initFromHtmlData` 由 `watch(htmlData,{deep:true})` 反复触发、
  每次把 `materialityConfig` 重置为载荷值 → 只在取数那一刻赋值会让阈值"时有时无"→ 改为缓存 `_autoConfig`
  并在 `initFromHtmlData` 末尾重新套用。
- **守卫** `diffReconcile/composables/__tests__/materialityAutoFetch.spec.ts`（19 例）：
  P1 三态语义（有效 PM / PM≤0 / 端点抛错 fail-open / projectId 缺失不发请求 / 字符串数值兼容）·
  P2 手工优先不变式（`is_overridden` 与已有载荷值都不得被覆盖）·
  P3 **接线存在性源码级断言**（宿主必须真传 `projectId`/`year`，防能力退化成零消费方）·
  P4 **TDZ 顺序断言**（`let _autoConfig` 行号必须早于首次 `initFromHtmlData` 调用行号）。
  回归：`diffReconcile` 域 **20 文件 / 42 passed / 0 failed**（基线 23 例，新增 19 例零回归）；3 文件 Vite 200。

**🔴 本轮另查出 2 处未修（跨循环写死文案，与 Task 37 同族，需科目归属裁决后一并处理）**

- `DiffChecklistMaster.vue` 两处写死「从 **D0-4** 带入」（按钮 + 空态提示），而 F0-4b 上应显示 F0-4；
  **且该带入功能本身仍是 TODO stub**（`GtConfirmationDiffChecklist.vue` 里只有 `console.log`）
  → 只改文案等于给 stub 化妆，应与实装一起做。
- `ReliabilityGrid` 工具栏写死「从 **D0-1** 带入电子回函」（F0-7 上应为 F0-1）。
  两处都可复用 Task 37 已建的 `alternativeMasterLabels` 范式（labels 常量 + prop 注入）。

**实测手法沉淀**

- **共享 Chrome 的 sessionStorage token 会掉** → 被重定向到 `/login` 时直接
  `fetch('/api/auth/login')` 写 `access_token` 再导航，比走 UI 快且稳。
- **`el-table` 固定列分区**：tbody 分散在 3 个 `.el-table__body` 里，按「表头列序 → td 下标」定位必失败
  → 改按 `placeholder` / `type=number` 特征定位输入框。
- **`wait_for` 的 MCP 参数序列化不稳**（`text` 需数组、`timeout` 需数字，多次报 invalid_type）
  → 直接用 `evaluate_script` 读 DOM 状态判断就绪。
- **终端失稳（PSReadLine 崩溃刷屏）时**改用 `control_pwsh_process start` + 脚本自己写盘 + `read_file` 读结果
  （memory 已记该铁律，本轮再次验证有效）。

## Wave 7 — 返工（2026-08-03 复盘新增）

> 立项依据：上轮把 8 项任务按「既有实现已覆盖」标 `[x]`（Task 6/9/12/13/15/16/17）——
> 该判断本身正确且有价值（F0 组件层比预估完整得多），但**新写的 5 个模块有 4 个零消费方**，
> 且矩阵的 P0 需求（R1.3/1.5/1.7）留在 TODO 注释里没接。

- [x] 23. 【P0】接通 F0 矩阵三个数据源
  - [x] 23.1 `bookAmounts` ← 新建 `f0MatrixDataSources.fetchTbAmountByWpCode`，按 wp_code 查 wp_id → 拉 render-config → 取任一 sheet 的 `project_context.tb_amount`。**不走 `fetchWorkpaperHtmlRows`**（它按 `_format` 匹配，与本需求无关）
  - [x] 23.2 `altTotals` ← **实证推翻上一版猜测**：数据在 `html_data._format='alternative-f0{5,6}-v1'` 的 `companies[].block{1..4}_rows[].voucher_amount`，**不在** `checklist_responses`。删 `extractAltTotalsFromResponses`（猜的 `{sheetCode}-block{n}-total` 键名全错），新建 `computeAltTotalsFromCompanies`
  - [x] 23.3 `manualOverrides`：`matrixOverrideItemId` + `parseManualOverrides` + 账面金额行改 `el-input` 可编辑 + `handleF0MatrixOverride` 写 `emit('save')`（空值=撤销覆盖回落自动值）+ 溯源提示条 + 「🔄 刷新取数」按钮
  - [x] 23.4 守卫 `f0MatrixDataSources.spec.ts`（26 例）：**源码级断言 4 个入参不得传 `undefined`** + 必须引用 `f0Sources`/`f0ManualOverrides` + 必须 `onMounted` 触发 + 矩阵调用块禁残留 TODO + import 路径实证（`@/utils/http` 非 `@/utils/api`）+ 运行时行为 12 例
  - _Requirements: 1.3, 1.5, 1.6, 1.7_
  - **实测**：3 个文件 Vite transform 全 200（**过程中修掉一个 Volar 查不出的 500** —— `@/utils/api` 不存在，正解 `@/utils/http`）；F0 全量 5 文件 193 测试绿

- [x] 24. 【P0】删除重复实现 `f0DiffChecklistEngine.ts` + 把其中真正有价值的能力合并进既有实现
  - [x] 24.1 grep 确认零消费方 → 删 `f0DiffChecklistEngine.ts` + `f0DiffChecklistEngine.spec.ts`（65 例）
  - [x] 24.2 **🔴 合并真正有价值的部分（不是简单删掉）**：既有 `useDiffChecklistData.sumSubTable` 用 `r.amount ?? 0`，而 **`??` 只挡 null/undefined，NaN/±Infinity 会穿透**让整条 A-I 公式链变 NaN（Excel 导入脏数据 / `parseFloat('abc')` / `1e400` 都会产生）→ 改 `Number.isFinite` 逐行过滤；`a_reply_amount`/`e_book_amount` 同样加 `safeAmount()` 归一
  - [x] 24.3 新建 `useDiffChecklistData.pbt.spec.ts`（63 例）：Property A/B/C 恒等式 **50 次随机输入**（精度 ≤ 0.01）+ Property D 脏数据不污染（7 例，含「原 `?? 0` 会穿透」的复现）+ Property E 子表 CRUD 后重算（4 例）+ 反向自检（2 例，固定样例手算比对证明测试真跑了公式）
  - _Requirements: 3.1, 3.2, 3.3_
  - **验证**：既有 21 例 + 新增 63 例 = 84 例全绿（NaN 防御改动零回归）。**净收益：删 2 文件、修掉既有实现一处真实缺陷、把 PBT 补在正确的位置**

- [x] 25. 【P0】`f0AltSupplierSeed.ts` 的 aux 余额匹配能力并入既有 `coordination/importFromSummary.ts`
  - [x] 25.1 删零消费方模块 `f0AltSupplierSeed.ts`（`extractUnrepliedSuppliers`/`seedAltProcedureFromSummary`/`filterSuppliersForAlt` 三个函数与既有 `importUnrepliedAsCompanies` + `defaultUnrepliedFilter` 重复）
  - [x] 25.2 **并入唯一有价值的能力**：`matchAuxBalance`（精确 > 双向包含 ≥4 字符 + 科目前缀限定）+ 新增 `fetchAuxBalances`（复用平台既有端点 `/api/projects/{id}/ledger/aux-balance/{code}`，G8/G9/G10 同款；按 `aux_type` 取行数最多的维度，**禁平铺全求和**因辅助维度冗余存储；失败 fail-open 返 `[]`）
  - [x] 25.3 `mapSummaryToAlternativeCompany` 加**可选** 3/4 参（`auxRows`/`accountPrefix`）+ 新增 `_balance_source: 'aux'|'summary'` 溯源标记；**不传 aux 时行为逐字不变**（零回归支点）
  - [x] 25.4 `importUnrepliedAsCompanies` 加 `options.auxAccountCode`/`auxYear`，返回 `auxMatchedCount`
  - [x] 25.5 **接线**（关键 —— 不能只写能力）：F0-5 传 `auxAccountCode='1123'`、F0-6 传 `'2202'`，toast 回报「其中 N 家期末余额已按辅助余额表校准」
  - [x] 25.6 改写 `f0AltSupplierSeed.spec.ts`（21 例）指向新位置 + **源码级断言 F0-5/F0-6 必须真传 `auxAccountCode`**（防能力再变零消费方）+ 断言旧模块已删
  - _Requirements: 2.1, 2.2, 2.3_
  - **业务价值**：汇总表 `amount` 是**发函金额**（抽样口径），替代程序「期末余额」应为**账面余额**，二者常有差异 → aux 命中时用精确账面值。**受益面 = D0/F0/G0/H0/K0/L0 六个循环**（能力放共享件而非 F0 私有）
  - **验证**：`confirmation` 全量 **53 文件 1006 例全绿**（唯一失败 `sendListSpec.spec.ts` 是并发会话未跟踪新文件，路径回退层数错，与本次无关）；3 文件 Vite 200

- [x] 26. 【P1】`emailDomainCheck.ts` 接入 `ReliabilityGrid.vue` 的 `email_domain` / `reply_email` 列
  - [x] 26.1 两列改 `email-cell` flex 布局（输入框 + 可靠性 tag 并排）：公司域名绿 / 私人域名红 / 无法识别灰，tag 带 tooltip 说明判定依据
  - [x] 26.2 「回函邮箱」列头加 ⓘ tooltip，正文取源模板注2 三条（私人信箱不可靠 / 工作邮箱域名核对 / 系统初判仍需审计师复核）
  - [x] 26.3 **🔴 修 `extractDomain` 的形态盲区**：原实现只认完整邮箱 `user@domain.com`，而 F0-7「邮箱域名」列的 placeholder 就是 `如 @company.com` → **裸域名一律判 unknown（灰色），等于该列接了也没用**。新增形态 B：`@domain.com` 去前缀 / `domain.com` 原样；含空格或无点的纯文本（如「待确认」）仍判 null
  - [x] 26.4 守卫扩到 61 例（+18）：裸域名 8 例 + 裸域名可靠性判定 5 例 + **源码级接线断言 5 例**（已 import / 两列各自渲染 tag / `type`·`label`·`tooltip` 三项都用上 + 反向自检）
  - _Requirements: 6.2_
  - **受益面**：D0/E0/F0/G0/H0/K0/L0 七个循环共用 `ReliabilityGrid`，一处改动全部受益
  - **验证**：reliability 既有 21 例 + F0 全量 = 5 文件 169 例绿；2 文件 Vite 200

- [x] 27. 【P1】舞弊迹象双真源收敛 —— **修法与立项时写的相反**
  - [x] 27.1 **实证推翻本任务原前提**：立项时写「删我抄的那份、改引用平台既有 `fraudRiskPresets.ts`」，
        而 openpyxl 直读六张 fraud-risk sheet（`D0-8` / `E0-8` / `F0-8` / `H0-7` / `K0-8` / `L0-7`）证明
        **19 条内容 md5 全等（`9abe16b804`）**，且**平台既有 `PRESET_FRAUD_ITEMS` 的文字与任何源模板都不一致**
        （原第 1 条「被审计单位管理层凌驾于内部控制之上」vs 源模板 A6「管理层不允许寄发询证函」）
        → 平台预置才是自造的那份，不能引用它
  - [x] 27.2 按源模板 A6:A24 **逐字重写** `PRESET_FRAUD_ITEMS` 19 条（文字用脚本从 xlsx 提取后写入，不手抄）
  - [x] 27.3 tooltip 归位：删自造的 `item_18_19_examples`（源模板无第 18/19 条举例），
        两条真实举例挂回它们真正解释的条目 —— **J18 讲回函率→第 14 条 / J19 讲独立性→第 15 条**
        （源模板把注写在上一行，属排版偏移，不是笔误）
  - [x] 27.4 `GUIDANCE_NOTES_D08` 四条改取源模板 A26 汇总行 + A31 编制说明第 1 条原文
  - [x] 27.5 删 `f0FraudRiskPush.F0_FRAUD_INDICATORS`，`createDefaultIndicators()` 改从预置派生
  - [x] 27.6 **修合并逻辑的传播缺陷**：`mergePresetWithExisting` 原样保留 userRow 的 `description`，
        而预置行 description 在 `FraudRiskChecklist` 里**只渲染文本不给输入框**（不是用户数据）
        → 预置文字更正永远传不到既有项目。改为始终取 `preset.description`，
        用户数据（`is_exist`/`source_ref`/`countermeasure`）照旧保留
  - [x] 27.7 守卫 `backend/tests/test_fraud_risk_presets_source_fidelity.py`（9 例，**以 xlsx 为裁决者**）：
        六表全等 + 19 条逐字 + tooltip 键集恰为两条 + 自造文字不得复活 + 双真源已删 +
        合并规则源码级断言 + 反向自检。**踩坑留证**：首版断言 `'item_18_19_examples' not in src`
        被自己的「更正记录」注释打红 → 必须 `_strip_ts_comments()` 后再断言（memory 铁律同款）
  - [x] 27.8 诚实修正既有测试：`useFraudRiskData.spec.ts` 原断言「预置行用户已编辑的 description 保留」
        锁的是旧行为，fixture 改为「存量落库的旧版自造文字必须被最新预置取代」
  - _Requirements: 4.3, 4.4_
  - **验证**：后端 9 例 + 前端 fraudRisk 16 例 + F0 全量 164 例全绿；4 文件 `get_diagnostics` 零诊断 + Vite 200
  - **受益面**：D0/E0/F0/H0/K0/L0 六个循环共用该预置，一处改动全部纠正

- [x] 28. 【P1】矩阵取值改按源模板公式，删掉编造的分摊逻辑
  - [x] 28.1 **源模板给出了确切公式**（`data_only=False` 直读 F0-1，比原计划的「无依据则返 null」强得多）：
        上区 R6 列语义 `E=账户/交易 · F=金额 · U=可确认金额 · Y=替代后可确认金额`；
        `R31=SUMIF(E,品种,F)` / **`R33=SUMIF(E,品种,U)`** / **`R36=SUMIF(E,品种,Y)`** / `R37=(R36+R33)/R30`
  - [x] 28.2 **推翻 requirements 两处描述**（已同步更正 R1.2/R1.3）：
        - R1.2 原写「S 列中 N 列=『相符』的行求和」→ 源模板是 `SUMIF(U)` **无相符过滤**。
          平台 `computeConfirmedAmount` 已按相符/不符/未回函派生 `confirmed_amount`，
          再叠一层过滤是双重口径；E0 的 `e0SummaryMatrix` 同样直接取 `confirmed_amount`
        - R1.3 原写「F0-5+F0-6 合计按品种归属」→ 源模板是 `SUMIF(Y)`，替代确认金额本就逐行记在上区 Y 列
  - [x] 28.3 删 `distributeAltAmounts`（F0-5 全归预付 / F0-6 平分应付票据+应付账款 = 编造）
        与 `sumConfirmedByCategory`（旧相符过滤口径）；`F0MatrixInput` 移除 `altF05Totals`/`altF06Totals`
  - [x] 28.4 **F0-5/F0-6 合计改作勾稽信号而非丢弃**（保住 Task 23.2 的取数价值）：
        新增 `checkAltConsistency`（上区 Y 列合计 ?= 两张替代程序底稿凭证金额合计，容差 0.01，
        三态 `ok`/`mismatch`/`no-data`）→ 不符即提示「Y 列漏填 / 替代程序底稿漏编」，
        **只报差异不改数字**
  - [x] 28.5 新增 `detectAltOverlapRows`：平台对「积极式+未回函」行令 `confirmed_amount = alt_confirmed`
        → 源模板 R37 公式会把这笔钱算两次。**不擅自改公式**（改了就不是源模板口径），
        改为如实提示风险行数由审计师复核 Y 列口径
  - [x] 28.6 守卫：`f0SummaryAggregation.spec.ts` 49 例（Property 2 改口径 + Property 8 勾稽 6 例 +
        双算识别 4 例 + `@ts-expect-error` 钉死入参已移除 + **反向自检「旧口径会得到 1400 而新口径 1650」**）；
        `f0MatrixDataSources.spec.ts` 扩到 33 例（源码级：矩阵入参禁含 alt 合计 / 勾稽与双算必须接线 /
        `distributeAltAmounts`·`sumConfirmedByCategory` 必须已删 / R33·R36 取列断言）
  - _Requirements: 1.3_
  - **验证**：F0 全量 164 例绿；`GtConfirmationSummary.vue` 零诊断 + Vite 200

- [x] 29. 【P1】撤回 6 条 F0 review-dialog prompt（三重无效，实证后判定不该补而该撤）
  - [x] 29.1 **纠正 memory 铁律的适用范围**：「四处缺一即空转」是 `wp_ai` 那条链路的（有 `_SUPPORTED_SECTIONS` 硬门）；
        `review_dialog.resolve_review_ai_prompt` 是 `.get()` 回退通用 prompt，**没有门** →
        缺登记只影响 prompt 质量、不造成 422/空转
  - [x] 29.2 撤回依据①**不可达**：section_id 来自 `useReviewDialog(props.sectionId)`。
        confirmation 目录**确实有**组件走这条路（`H0-5-alternative` / `H0-5-conclusion` /
        `K0-5-alternative` / `K0-6-alternative` / `K0-6-conclusion` 五个 `GtReviewTrigger`），
        **但 F0 的组件一个都没接** → 那 6 条无论内容对不对都不会触发
  - [x] 29.3 撤回依据②**F0-1 段划分错**：源模板「三、审计说明」实为 **5 段**
        （`S29` 对询证函保持的控制的说明 / `W29` 对误差的分析 / `S33` 对以传真或电子邮件形式收到的回函的
        可靠性的考虑 / `S34` 针对不符事项的程序 / `S37` 针对未回函的替代程序）。
        原 4 条既自造了不存在的「第三方平台评估」段，又漏了「对误差的分析」与「针对不符事项的程序」
  - [x] 29.4 撤回依据③**F0-4 压根没有审计说明区**：源模板 F0-4 只有 9 列明细 + R21 合计行
  - [x] 29.5 删除 6 条 + 在原处留撤回依据注释；守卫 `backend/tests/test_f0_review_prompts.py`（8 例）：
        撤回项不得回填 + 全量扫描（含 `**{...}` 推导式）不得出现 `f0-` 键 +
        「凡登记 f0- prompt 必须有前端消费方」+ **「F0 组件一旦接了 review-dialog 就打红提醒补回 prompt」** +
        源模板 5 段/F0-4 无说明区两条事实冻结 + `resolve_review_ai_prompt` 必须保持回退语义
  - [x] 29.6 **顺带留证源模板笔误**：`S33` 写「（F0-6）」而可靠性验证表实为 **F0-7**（F0-6 是应付及采购替代程序）
        → 守卫按原文断言，禁「顺手修正」
  - _Requirements: 9.1_
  - **踩坑留证**：抽 `_SECTION_PROMPTS` 键集不能用 `\{(.*?)\n\}` 截字典体 —— prompt 值本身是多行括号表达式，
    非贪婪会停在第一条 entry 的收尾括号上（实测只抽到 10 个键）→ 改「声明处 → 下一个顶层 `def`」切片
  - **遗留（需用户裁决，不在本 spec 内）**：若要给 F0 做源模板忠实的分段审计说明，等于让 F0 脱离
    共享 `ConfirmationNotes`（平台通用 5 段：总体/异常/未回函/替代/其他）。F0 的 5 段与平台 5 槽
    **不能双射**，硬塞就是「压扁」反模式；且 F0 已有 `ai-generate-notes` 批量预填 →
    再加一个 F0 专属说明区会变成两处审计说明双录入。属共享组件级决策
  - _Requirements: 9.1_

- [x] 30. 【P2】CI job `f0-confirmation-linkage` 对齐平台形态并本地验证可跑
  - [x] 30.1 统计既有 29 个前端 job 的形态分布 → 主流（15/29）是
        `setup-node` 带 `cache: npm` + `cache-dependency-path: audit-platform/frontend/package-lock.json`
        + `npm ci` 配 `working-directory` → 本 job 原属少数派（无缓存），已补齐
  - [x] 30.2 两个 vitest 步骤本地实跑：`__tests__/f0` 4 文件 164 例绿；
        `diffChecklist` 2 文件 84 例绿（含 Task 24 补的 PBT）
  - [x] 30.3 加挂三步：fraudRisk 前端回归 + `test_fraud_risk_presets_source_fidelity.py`（需 openpyxl）
        + `test_f0_review_prompts.py`
  - [x] 30.4 `yaml.safe_load` 验证：109 个 job 数量不变，本 job 10 步解析正常
  - _Requirements: 9.3_

- [x] 31. 【P2】真实库复核（只读）—— 一半可核、一半全库无数据，如实分开报告
  - [x] 31.1 新建 `backend/scripts/diagnose/verify_f0_matrix_live.py`（只读，从前端常量抽 wpCode/hint 再与库对账，
        防「脚本与实现各说一套」）
  - [x] 31.2 **账面金额侧（真实数据，全部通过）**：`report_config` 实证
        `BS-008=TB('1123','期末余额')` / `BS-044=TB('2201',…)` / `BS-045=TB('2202',…)`，
        **四准则各自唯一**，与 `F0_BOOK_AMOUNT_SOURCES` 的 hint 逐字一致；「本期采购」正确声明 `null`。
        4 个有 F0 底稿的项目实际余额：
        `0ec33ac9` 13,576,792.21 / 101,893,600.00 / 254,189,472.38 ·
        `2aa00f57` 2,603,836.86 / **30,058,093.28** / **534,617,953.54**（与 memory 记的 F3/F4 活体值吻合）·
        `c8621493` 127,955.76 / **0.00** / 2,141,627.22 · `f064f5e4`(2024) 三项全无 → `bookMissing`。
        实证了「余额为 0 ≠ 无此科目」两态可区分（前者 book=0 比例显示「-」，后者进 bookMissing）
  - [x] 31.3 **上区 grid 侧：全库零函证明细行** —— 扫 `_format LIKE 'confirmation%'` 只有 1 张 sheet
        （`D0` 的 `函证结果汇总表D0-1`）且 `rows=0`，F0 的 12 个 workpaper `html_data` 全为空。
        → 「品种列和 == 该品种全部行之和」**无法用真实数据复核**，脚本如实打印结论，
        **不用自造 fixture 冒充实测**（那只是把假设重复一遍）。脚本已内置真实明细分支，
        待有数据后重跑即可补齐
  - _Requirements: 9.2_

## Wave 8 — 复盘修复（2026-08-04，Task 20.2 实测挖出的两个 P0 + 三项建议）

> 立项经过：做 Task 20.2（F0-5 从 F0-1 带入 + aux 精确余额）时发现 aux 路径**从未生效过**，
> 逐层下挖出两个独立缺陷，其中一个是平台级。三项修法在落地时被真实数据推翻/收窄。

- [x] 32. 【P0·平台级】`get_aux_balance` 由精确等值改前缀匹配
  - [x] 32.1 **根因**：`ledger_penetration_service.get_aux_balance` 写 `account_code == account_code`，
        而辅助余额数据几乎全落在子科目。全库实测：**子科目 810,884 行 vs 精确四位码 1,507 行**
        → 精确等值漏掉 **99.8%**。该项目 `1123` 只有 `1123.01`/`1123.03`、`2202` 只有
        `2202.01~.98`，一级码**一条都查不到** → 四个消费方（F0-5/F0-6 aux 校准 + G8/G9/G10
        辅助核算取数）全部静默取空
  - [x] 32.2 **判据是三方一致的、本方法是唯一例外**：共享件 `four_table/aux_aggregation.py`
        铁律 3 明写「账套里科目通常落在子科目，故用前缀匹配而非精确等值」；同族端点
        `GET /ledger/aux-balance-detail` 早已是逐字同款表达式。故按既有判据修正
        （含点号仍精确等值），并把 `account_code` 加进投影（前缀匹配后 `accountPrefix`
        限定需要真实子科目码，原先回退成调用方传的父码）
  - [x] 32.3 守卫 `backend/tests/test_aux_balance_subaccount_prefix.py`（10 例）
        + **变异检验**：改回精确等值 → **6/10 打红**且红在前缀断言上（非空转）
  - [x] 32.4 零回归：HEAD 换文件法证明两侧失败集合逐条相同（3 个预存在）、**新增 0**
  - [x] 32.5 运行态实证：端点 **0 行 → 182 行**，目标单位余额 114,800.00
  - _Requirements: 2.3_

- [x] 33. 【P0】`fetchAuxBalances` 的 apiProxy/http 形态错配
  - [x] 33.1 `const { data } = await api.get(...)` —— `api`（`@/services/apiProxy`）
        **直接返回业务数据**，该端点返回**数组**、数组无 `data` 属性 → 恒 `undefined` → 恒返回 `[]`。
        浏览器实测：同一 URL `api.get` 返回 182 元素数组而解构值为 `undefined`。
        **与 Task 20.1 是同一类缺陷、方向相反**（那次是用 `http` 却按 apiProxy 形态读）
  - [x] 33.2 修为直接取返回值 + 保留对象形态 fallback（未来换信封不会再断）
  - [x] 33.3 运行态实证：toast 由「已带入 2 个」变为
        「已带入 2 个，**其中 1 家期末余额已按辅助余额表校准**」
  - _Requirements: 2.3_

- [x] 34. 【P0-1】`matchAuxBalance` 跨子科目求和 —— **两次被真实数据推翻，最终形态与首版相反**
  - [x] 34.1 首版：`.find()` → `filter + sum`（一个单位可能在多个子科目各有余额；
        实测 2202 有单位横跨 `.01/.02/.03/.97/.98` **5 个子科目**且只有 `.98` 带金额）
  - [x] 34.2 **推翻①：不得按 `(科目码, 单位名)` 去重**。我一度加了去重（怕数据集版本冗余双算），
        实测证伪 —— 同一 `(2202.02, 某客户)` 在 **active dataset 内**有 4 行，
        `aux_dimensions_raw` 分别是 `客户+成本中心:采购部` / `:渝北总店` / `:长寿美丽泽京店`
        / `客户+成本中心+集团内外`，金额 `2,601,247.80 / 268,355.69 / 0 / 0`，合计 2,869,603.49。
        **它们是不同维度组合、不是重复行**，去重会只留一条 → **丢钱**。
        数据集冗余**已由后端 `get_active_filter` 消除**（实测该单位 8 行→4 行、`1123` 364→182），
        前端再去重是重复且有害的
  - [x] 34.3 **推翻②：包含匹配路径必须要求 aux 单位名唯一**。实测同一科目族下
        「重庆和平药房连锁有限责任公司医药保健品分公司」与「重庆市黔江区和平药房连锁有限责任公司」
        **是两个不同单位**且互相包含子串 → 对包含命中做求和会把别人的钱算进本单位
        （比原 bug 更严重）。改为 `distinctNames.size === 1` 才求和，多义时返 `undefined`
        回退发函金额（宁缺勿造）
  - _Requirements: 2.3_

- [x] 35. 【P0-2】aux_type 选择规则与后端对齐
  - [x] 35.1 新增导出 `pickAuxType` + `AUX_TYPE_PREFERRED_KEYWORDS`，优先级改
        **关键词 > 余额 > 行数**，与后端 `four_table/aux_aggregation.pick_aux_type` 逐条同源
  - [x] 35.2 **原「行数最多」是碰巧对**：实测该项目 `1123` 客户 **184 行** vs 成本中心 **180 行**
        （仅 4 行之差）→ 一旦成本中心行数更多，替代程序期末余额就会静默按成本中心维度校准
  - [x] 35.3 守卫交叉锁死前后端关键词表逐条一致（读 py 源码比对）
  - _Requirements: 2.3_

- [x] 36. 【P1-2】`_balance_source` 孤儿字段接线
  - [x] 36.1 根因在**共享工厂** `createAlternativeConfirmationData.importCompanies` 的
        **字段白名单**构造 → 该字段被静默丢弃、落库恒 null → 审计师看不出某家的期末余额
        是账面精确值还是发函金额（两个口径常有差异）
  - [x] 36.2 在 `AlternativeCompany` 正式声明该字段（optional → 其余六枢纽零回归），
        工厂显式透传（只透传已声明的 `_` 前缀溯源字段，不做整体 spread）
  - [x] 36.3 守卫含反向自检：工厂若改成 `...item` 整体展开则打红提醒重评
  - _Requirements: 2.3_

- [x] 37. 【P2】F0-5/F0-6 主表文案接既有共享机制
  - [x] 37.1 复用 `alternativeD05/alternativeMasterLabels.ts`（G0 spec 已建，其 docstring
        早已把 F0-5/F0-6 登记为待接入方，原文「改动量 = 一个 labels 常量 + 一处 prop 传参」）
  - [x] 37.2 新建 `composables/f0MasterLabels.ts`，文案**全部取自源模板实证**：
        `A5 供应商名称：` / F0-5 `K11 本期付款检查比例` / F0-6 `K11 本期入库检查比例`
        / 索引号占位符 `F0-` / 带入按钮「从 F0-1 带入」（原显示「从 D0-1 带入」）
  - [x] 37.3 两宿主各传 `:labels`（不传等于回落 D0-5 默认值 = 改了也看不到）
  - _Requirements: 7.1_

- [x] 38. 【守卫】扩 `f0AltSupplierSeed.spec.ts` 覆盖上述五项
  - [x] 38.1 新增 8 例（跨子科目求和 / 多维度组合不去重 / 包含匹配多义拒绝 /
        `pickAuxType` 优先级 / 前后端关键词表交叉锁死 / apiProxy 形态 / `_balance_source`
        透传 / 主表文案），并诚实删掉首版两条**锁定错误行为**的去重断言
  - [x] 38.2 **踩坑留证**：两条负向断言（禁 `const { data } =` / 禁「从 D0-1 带入」）
        首轮被**自己的说明注释**打红 → 加 `stripComments()` + 反向自检（memory 铁律同款）
  - [x] 38.3 回归：前端 `confirmation` **71 文件 1510 例全绿**（基线 1502，新增 8 例零回归）；
        后端新守卫 10/10，`ledger_penetration` 3 个失败已证预存在
  - _Requirements: 9.1, 9.2_

## Notes

### 本轮偏离与遗留

- **P1-1「apiProxy/http 形态错配平台守卫」按用户裁决独立立项**（不在本 spec 内做）：
  该坑一天内出现两次、方向相反，且 `get_diagnostics` / vitest / Vite 200 **四层全绿**
  （响应体在 TS 里是 `any`）。判据是机械可自动化的 ——
  `import { api } from '@/services/apiProxy'` ⇒ 禁 `const { data } = await api.get`；
  `import http from '@/utils/http'` ⇒ 必须 `.data`。半径为全仓 2000+ 文件，故独立 spec。
- **G8/G9/G10 的历史误判需回查**：它们取不到 aux 时提示「科目 X 无辅助核算余额（年度 Y）」。
  端点修好前这条提示对**几乎所有项目**都会出现，很可能被当成「该项目确实没有辅助核算」接受了。
  修复自动生效，但值得抽一个项目实测确认。

### 与 E0 spec 的边界

- `e0-confirmation-completion`（18/18 已完成）与本 spec 无冲突 —— E0 的联动是银行账户×品种维度，F0 的联动是供应商×科目维度，完全独立。
- `e0-send-list-dedicated-components`（0/18）的 send-list 范式（专属 componentType + 16 列结构化）**不适用 F0** —— F0 的函证对象是统一的供应商（一函覆盖多品种），发函清单合并在 F0-1 上区而非独立 sheet。
- 本 spec 的 Wave 4 B50 推送是**七枢纽共享件**（D0/E0/F0/G0/H0/K0/L0 均受益），但本 spec 只实现 F0 侧接线，共享件若已由其他 spec 建好则直接复用。

### 共享组件改造的隔离策略

F0 的结构化增强涉及 6 个**共享** confirmation 组件（summary/diff-checklist/diff-reconcile/reliability/fraud-risk/followup）。隔离策略：
- 所有 F0 专属逻辑必须在 `resolveConfirmationCycle(wpCode) === 'F0'` 门控下
- 其他循环（D0/G0/H0/K0/L0）的行为零改动，由门控保证
- 守卫包含「非 F0 循环调用时返回原样」反向自检

### 已知风险

1. `GtConfirmationSummary.vue` 已是大文件（1200+ 行），注入矩阵聚合需要拆 composable 避免膨胀
2. `fetchWorkpaperHtmlRows` 有两个静默失效点（memory 已记），取 F1/F3/F4 tb_amount 应改走 render-config 的 `project_context.tb_amount`（每个 sheet 的 `html_data` 都有）
3. F0-7 可靠性验证组件是七循环共享，结构化列若做成 F0 专属会让其他循环看不到 → 设计为平台级能力但默认关闭，F0 通过 `cycleConfirmationMeta` 的 `reliabilityStructured: true` 开启

## Wave 8 — 复盘修复（2026-08-04，Task 20.2 实测挖出）

> 立项依据：做 Task 20.2（F0-5 从 F0-1 带入 + aux 精确余额）时，实测发现
> **aux 校准路径从未生效** —— 期末余额落库的是汇总表发函金额 1000，而不是
> 辅助余额表的账面值 114,800。逐层排查挖出**两个独立的 P0**，都不在原计划内。

- [x] 32. 【P0·平台级】`get_aux_balance` 科目码精确等值 → 前缀匹配
  - [x] 32.1 **根因**：`ledger_penetration_service.get_aux_balance` 写
        `account_code == account_code`，而辅助余额数据几乎全落在**子科目**。
        全库实测（2026-08-04）：`tb_aux_balance` 落在子科目 **810,884 行** /
        落在精确四位码仅 **1,507 行** → 精确等值漏掉 **99.8%** 的数据。
        该项目 `1123` 只有 `1123.01`/`1123.03`、`2202` 只有 `2202.01~.98`，
        一级码**一条都查不到**
  - [x] 32.2 **判据是三方一致的，本方法是唯一例外**：
        ① 平台共享件 `four_table/aux_aggregation.py` **铁律 3** 明写「账套里科目
           通常落在子科目，故用前缀匹配而非精确等值」
        ② 同族端点 `GET /ledger/aux-balance-detail` 早已是这个表达式（逐字同款）
        ③ 全库数据分布（见 32.1）
  - [x] 32.3 修法：含点号（`1123.03`）仍精确等值 / 一级码走 `LIKE '{code}%'`；
        并把 `account_code` 加进投影（前缀匹配后 `accountPrefix` 限定需要真实子科目码）
  - [x] 32.4 守卫 `backend/tests/test_aux_balance_subaccount_prefix.py`（10 例）
        + **变异检验**：改回精确等值后 **6/10 打红**且红在前缀断言上（不是空转）
  - [x] 32.5 零回归：**HEAD 换文件法**证明两侧失败集合逐条相同（3 个预存在），新增 0
  - [x] 32.6 运行态实证：端点由 **0 行 → 182 行**，目标单位余额 114,800.00
  - **受益面 4 个消费方**：F0-5/F0-6 的 aux 校准 + G8/G9/G10 辅助核算取数
    （`1503`/`1519`/`2101`）—— 后三者此前提示「科目 X 无辅助核算余额」，
    对**几乎所有项目**都会出现，很可能被当成「该项目确实没有辅助核算」接受了
  - _Requirements: 2.3_

- [x] 33. 【P0】`fetchAuxBalances` 的 apiProxy/http 形态错配
  - [x] 33.1 **根因**：`const { data } = await api.get(...)` —— `api` 来自
        `@/services/apiProxy`（**直接返回业务数据**），该端点返回**数组**，
        数组无 `data` 属性 → `data === undefined` → `raw = []` → 恒返回 `[]`
  - [x] 33.2 浏览器实测：同一 URL `api.get` 返回 **182 元素数组**，而解构出的
        `data` 是 `undefined`。**与 Task 20.1 的根因是同一类、方向相反**
        （那次是用 `@/utils/http` 却按 apiProxy 形态读）
  - [x] 33.3 修法：直接取返回值；保留对象形态回退（`data`/`items`/`rows`）
        以防将来端点改成信封形态又静默失效
  - [x] 33.4 运行态实证：带入 toast 由「已带入 2 个」变为
        「已带入 2 个，**其中 1 家期末余额已按辅助余额表校准**」
  - _Requirements: 2.3_

- [x] 34. 【P0】`matchAuxBalance` 跨子科目求和 —— **两次被真实数据推翻**
  - [x] 34.1 原实现用 `.find()` 取**第一个**命中行 → 少算。实测 `2202` 有单位
        横跨 `2202.01/.02/.03/.97/.98` **5 个子科目**且只有 `.98` 带金额
        （−5,143,381.25），取第一条会拿到 0
  - [x] 34.2 **🔴 第一版修法（按 `科目码|单位名` 去重后求和）被实证推翻**：
        同一 `(科目码, 单位名)` 的多行**不是重复行**，而是**不同辅助维度组合**——
        实测 `2202.02` 某客户在 **active dataset 内**有 4 行，`aux_dimensions_raw`
        分别是 `客户+成本中心:采购部` / `:渝北总店` / `:长寿美丽泽京店` /
        `客户+成本中心+集团内外`，金额 `2,601,247.80 / 268,355.69 / 0 / 0`，
        合计 **2,869,603.49**。按 `科目码|单位名` 去重会只留一条 → **丢钱**
  - [x] 34.3 数据集版本冗余（同一行 `dataset_id` NULL 与 active 各一份）
        **已由后端 `get_active_filter` 处理**（实测该单位 8 行 → 4 行、
        `1123` 364 行 → 182 行）→ 前端再去重是重复且有害的，已移除
  - [x] 34.4 **🔴 包含匹配路径改为「只认唯一单位名」**：实测同项目
        `2202` 下有**两个不同单位**都含「和平药房连锁有限责任公司」
        （`重庆和平药房连锁有限责任公司医药保健品分公司` 与
        `重庆市黔江区和平药房连锁有限责任公司`）→ 包含匹配 + 求和会把
        **两家公司的钱加在一起**，比原 bug 更坏。多义时返 `undefined`
        回退发函金额（宁缺勿造）
  - [x] 34.5 守卫含 5 条真实数据用例（5 子科目求和 / 4 维度组合不去重 /
        跨单位多义返 undefined / 唯一单位仍求和 / 前缀隔离）
  - _Requirements: 2.3_

- [x] 35. 【P0】`fetchAuxBalances` 的 aux_type 选择规则对齐后端
  - [x] 35.1 原按「行数最多」选维度；后端 `pick_aux_type` 是
        **关键词 > 余额 > 行数**。实测该项目 `1123` 下「客户」**184 行** /
        「成本中心」**180 行** —— 仅差 4 行，行数规则**碰巧**选对了客户；
        一旦成本中心行数更多，替代程序期末余额会静默按成本中心校准
        （金额不对而界面无任何提示）
  - [x] 35.2 新增导出纯函数 `pickAuxType` + `AUX_TYPE_PREFERRED_KEYWORDS`
  - [x] 35.3 守卫**读后端 `aux_aggregation.py` 源码交叉锁死**关键词表逐条一致
        （改一侧另一侧必红）+ 反向自检「按行数会选错」
  - _Requirements: 2.3_

- [x] 36. 【P1】`_balance_source` 孤儿字段接线
  - [x] 36.1 **根因在共享工厂**：`createAlternativeConfirmationData.importCompanies`
        按**字段白名单**构造公司行，`_balance_source` 不在其中 → 静默丢弃 →
        落库恒 `null` → 审计师看不出某家期末余额是 aux 账面值还是发函金额
        （而这两个口径常有差异，正是本能力要解决的问题）
  - [x] 36.2 在 `AlternativeCompany` **正式声明**该字段（optional → 其余六枢纽
        零回归），不靠 `as any` 强转
  - [x] 36.3 工厂只透传**已声明**的 `_` 前缀溯源字段，不做整体 `...item` spread
        （防把上游临时字段一并写进持久化载荷）
  - [x] 36.4 守卫含反向自检「工厂确实是白名单构造」——若将来改成整体 spread
        会打红提醒重新评估
  - _Requirements: 2.3_

- [x] 37. 【P2】F0-5/F0-6 主表文案接 `alternativeMasterLabels`
  - [x] 37.1 **不新建机制**：共享件 `alternativeMasterLabels.ts` 由 g0 spec 建好，
        其 docstring 已把 F0-5/F0-6 登记为待接入方并写明
        「改动量 = 一个 `labels` 常量 + 一处 prop 传参」
  - [x] 37.2 新建 `composables/f0MasterLabels.ts`，**文案全部源模板实证、禁自造**：
        - `供应商名称` ← 源 `F0-5!A5` / `F0-6!A5`「供应商名称：」（去冒号）
        - `本期付款检查比例` ← 源 `预付及采购替代程序F0-5!K11` 逐字
        - `本期入库检查比例` ← 源 `应付及采购替代程序F0-6!K11` 逐字
        - `从 F0-1 带入`（原写死 D0-1）· 占位符 `F0-`（原 `D0-`）
  - [x] 37.3 两个宿主各传 `:labels`（**只写常量不传 prop 等于改了看不到** ——
        与本 spec Wave 7 抓的「零消费方」同族）
  - [x] 37.4 🔴 `receipt`/`shipment` 两个 `type` 值**不改**（master 的
        `getCheckRatio` prop 签名依赖它），只改 `label`
  - _Requirements: 8.1_

- [x] 38. Wave 8 回归与守卫
  - [x] 38.1 前端 `confirmation` 全量 **71 文件 / 1510 例全绿**
        （基线 1502 → 新增 8 例，新增失败 0）
  - [x] 38.2 后端新守卫 10/10 绿；`test_ledger_penetration.py` + `test_drilldown.py`
        3 个失败**经 HEAD 换文件法证明为预存在**（两侧集合逐条相同）
  - [x] 38.3 **守卫自身踩坑留证**：首版两条负向断言被自己的**解释性注释**打红
        （注释里写了「不得出现 `从 D0-1 带入`」「不得解构 `{ data }`」）→
        必须 `stripComments()` 后再断言，且**配反向自检**证明剥离没有空转
        （memory 已记同款铁律，本轮第 N 次踩中）
  - _Requirements: 9.1, 9.2, 9.3_

### 🔴 Wave 8 沉淀的判据（供其他循环复用）

1. **「一级科目码取不到辅助余额」不是数据问题，先查匹配是否用了精确等值** ——
   平台判据是前缀匹配，写在 `four_table/aux_aggregation.py` 铁律 3。
2. **apiProxy vs http 形态**：用 `api`（apiProxy）直接拿返回值；用 `http`
   （`@/utils/http`）才需要 `.data`。四层验证全绿查不出（响应体在 TS 里是 `any`），
   **只有浏览器能发现**。已请用户另立平台级守卫 spec 做全仓扫描。
3. **辅助余额「多行」有三种成因，处置完全不同**：
   ①数据集版本冗余 → 后端 `get_active_filter` 已处理，前端**不要再去重**
   ②同一单位跨**子科目** → 应求和
   ③同一 `(科目码,单位名)` 跨**辅助维度组合**（`aux_dimensions_raw` 不同）→ 应求和
   判据 = 查 `aux_dimensions_raw` 与 `dataset_id`，**不能靠字段名猜**。
4. **按名包含匹配 + 求和 = 危险组合**：必须先断言命中的 aux 单位名**唯一**，
   否则会把总公司与分公司（或同名族企业）的余额加在一起。
5. **「N 个候选里选一个」的规则要与后端同源并交叉锁死** —— 前端按行数、后端按
   关键词，在数据接近时（184 vs 180）前端**碰巧对**，改天就静默错。
