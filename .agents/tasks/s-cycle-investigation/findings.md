# S 类（专项/IPO/再融资）底稿现状与缺口调查报告

> 只读调查，未修改任何代码。证据以 `文件路径:行号 / 符号名` 支撑。区分【已确认】与【未能验证】。
> 调查日期：基于当前工作区 HEAD 快照。

---

## 0. 摘要（先看结论）

**核心判断：用户"S 类还没做专属组件"这一前提，与现状存在分化。真实情况是三种状态并存，需分别对待：**

- **（A）bundle 不是空壳**：S32/S33/S34/S35 四个 bundle 组件是**真实现**（聚合 tab + 清单总览 + 法规溯源 + 进度仪表盘），但 **bundle 内每个子底稿并没有"专属组件"**——它们统一复用通用 `GtAProgramConsole`（程序表中控台）+ 少量子检查表，由 render-config 驱动。S34 的公式引擎/跨引用只是**两张子表的试点**，不是完整覆盖。
- **（B）单项 S 底稿大多有专属组件且较完整**：S3/S4/S5/S6/S12/S13/S14/S15/S20/S21 都有成体系的多 sheet 专属 Vue 组件（真实现）。
- **（C）真正"缺专属组件"的是另一批**：S1/S2/S8/S9/S10/S11/S16/S17 在 `wp_code_overrides.json` 里被映射到**通用兜底** `a-program-console`；其中 S1/S8/S9/S10/S17 虽然**写了**专属子 sheet 组件（`s-checklist/` 目录 13 个 .vue），但这些组件**从未被任何活动代码 import/dispatch**——是**孤儿组件（已写未接线）**。S2/S11/S16 连专属子组件都没有。

**用户最在意的"关联联动 / 风险导向 / 底稿裁剪 / 委派"四条：**

| 维度 | 现状 | 证据级别 |
|---|---|---|
| 关联联动（S↔D/A/B 数据串联） | **几乎缺失**。S 类 `linked_workpapers` 全 92 条为 `None`；无 WORKPAPER_SAVED 订阅；S34/S35 的"跨引用"**只是 tab 跳转/全局导航，不是取数或数据联动** | 已确认 |
| 风险导向 | **部分**。bundle 的清单适用性仅由"底稿是否生成"驱动，未接 B 循环风险评估结果 | 已确认 |
| 底稿裁剪 | **部分（声明层有，执行层断裂）**。`applicable_when` 字段已在映射表写好，但生成匹配器 `match_workpapers` 不识别它，前端 `isNotApplicable` 只认 `consolidated`，不认 `business_category` | 已确认 |
| 委派人员 | **仅循环级，无底稿级**。`assignment_service` 按 `assigned_cycles`（如 "S"）分派，不能精确到单个 S 底稿 | 已确认 |

---

## 一、S 类底稿清册与编制逻辑

### 1.1 模板文件清册（`backend/wp_templates/S/`，共 96 个文件）

按分组（文件系统实测，`Get-ChildItem -Recurse`）：

**S1~S21 单项特殊审计考虑（24 个文件）**
- S1 违反法规行为（.xlsx）、S2 期初余额（.xlsx）、S3 会计政策变更/前期差错/估计变更（.xlsx）
- S4 非货币性资产交换（.xlsx）、S5 债务重组（.xlsx）、S6 大股东资金占用/违规担保（.xlsx）
- S8 租赁（.xlsx）、S9 电子商务（.xlsx）、S10 环境事项（.xlsx）、S11 利用服务机构（.xlsx）
- S12 利用专家（.xlsx）、**S12A 评估专家工作报告（.docx）**、S13 利用管理层专家（.xlsx）
- S14 会计估计（.xlsx）、S15 每股收益/净资产收益率（.xlsx）、S16 套期活动（.xlsx）
- **S17 非经常性损益（.xls — 旧版二进制格式）**
- S20 营业收入扣除核查（.xlsx）、S21 数据资产（.xlsx）

**S32 舞弊核查（13 个文件，S32-1~S32-13）** — IPO 反舞弊专项核查
**S33 应对14号公告核查（11 个文件，S33-1~S33-9 + S33-1程序修订说明.docx）**
**S34 IPO 首发审核（约 43 个文件，S34-0~S34-41 + S34-1-1 信息披露豁免专项核查意见.docx）**
**S35 再融资核查（5 个文件，S35-1~S35-5）**

格式差异【已确认】：绝大多数 `.xlsx`；`.docx` 三个（S12A、S33-1程序修订说明、S34-1-1）；`.xls` 一个（S17，旧版）。

### 1.2 代表性模板的 sheet 构成与编制逻辑（openpyxl 实测）

| 模板 | sheets（实测 dims） | 编制逻辑类型 |
|---|---|---|
| **S20 营业收入扣除**（`S20...202504.xlsx`） | 单 sheet `营业收入扣除情况核查` 78×9 | 计算/核查型（注册制营收扣除） |
| **S15 每股收益/ROE** | `表头` 20×8 / `审计程序S15` 30×8 / `审定表S15-1` 13×8 / `基本EPS S15-2` 32×8 / `稀释EPS S15-3` 32×8 / `净资产收益率S15-4` 60×11 | **计算型**（EPS/ROE 多表计算，有审定表） |
| **S34-16 第三方回款** | `目录` / `S34-16程序表` 31×8 / `S34-16-1第三方回款情况检查表` 29×14 / `S34-16-2同行业对比表` 29×9 / `GT_Custom` | 程序表 + 2 张公式子检查表 |
| **S34-35 收入核查** | `S34-35收入核查程序表` 99×13 / `【附】各文件相关要求` 12×4 / `GT_Custom` | **纯程序表型**（宽表 13 列，无子检查表） |
| **S1 违反法规** | `表头` / `违反法规行为S1` 78×9 / `S1-1对法律法规考虑记录表` 95×10 / `S1-2沟通记录` 36×5 | 程序表 + 记录表 + 沟通记录（说明/记录型） |
| **S5 债务重组** | `表头` / `债务重组审计程序S5` 57×6 / `审定表S5-1` 49×9 / `损益确认时点S5-2` 36×11 | 程序表 + 审定表 + 时点判断表 |

**编制思路归纳**：
- **程序表型**（S1/S2/S8/S10/S11/S13/S16/S34 大多数/S32/S33）：逐条审计程序 + 执行记录 + 结论，LEAP 式。
- **检查表/逐项核查型**（S4/S5/S6/S9/S12/S14/S34-16 子表/S20/S21）：结构化字段表单。
- **计算型**（S15/S17）：含公式计算与审定表（S15-1 / S17 税影响）。
- **说明/文档型**（S12A/S33-1说明/S34-1-1，.docx）：Word 文档。

> 【已确认】`GT_Custom` / `目录` / `表头（请先填写）` 是系统元数据/占位 sheet，统一不渲染（见 `S34_TAB_CONFIG.ts` 注释、archived design §1.1）。

---

## 二、HTML 组件实现现状（最关键）

### 2.1 componentType 映射全景（`backend/app/data/wp_code_overrides.json:1370-1497`）

| wp_code | componentType | 组件/归属 |
|---|---|---|
| S1 / S2 / S8 / S10 / S10-1/2 / S11 / S13 / S16 / S17(+子) / S9(+子) | `a-program-console` | **通用兜底**（无专属顶层组件） |
| S3 | `s3-policy-change` | 专属 |
| S4 / S4-1/2 | `s4-nonmonetary-exchange` | 专属 |
| S5 / S5-1/2 | `s5-debt-restructuring` | 专属 |
| S6 / S6-1 | `s6-fund-occupation` | 专属 |
| S12 | `s12-cpa-expert` | 专属；S12A → `word-template` |
| S13 | `s13-mgmt-expert` | 专属（注：S13 同时被标 a-program-console？见下） |
| S14 | `s14-accounting-estimate` | 专属 |
| S15 | `s15-eps-roe` | 专属 |
| S20 | `s20-revenue-deduction` | 专属 |
| S21 | `s21-data-asset` | 专属 |
| S32 / S33 / S34 / S35 | `s32-fraud-bundle` / `s33-ann14-bundle` / `s34-ipo-bundle` / `s35-refinance-bundle` | **bundle 专属** |
| S32-*/S33-*/S34-*/S35-* 全部子码 | `skip` | 不独立渲染，由 bundle 内部聚合 |
| S12A / S33-REV / S34-1-1 | `word-template` | Word 编辑器 |

> 注【已确认】：`overrides.json` 里 S13 = `s13-mgmt-expert`（1377 行）。archived design 曾计划 S13 = a-program-console，但现行映射是专属组件。以现行 overrides 为准。

### 2.2 单项/bundle 组件实现深度判定（行数 + 字段绑定实测）

组件目录行数实测（`Get-ChildItem | Measure-Object -Line`）：

| componentType | 主组件 + 子组件（行数） | 判定 |
|---|---|---|
| s3-policy-change | GtS3PolicyChange 316 + 8 子（Adjudication/EstimateChange/Ifrs9/15/16Adjust/PolicyError/SimplifiedRetro1/2，204~344 行） | **真实现** |
| s4-nonmonetary-exchange | GtS4 261 + S4Adjudication 363 + CommercialSubstance 341 + Program 261 | **真实现** |
| s5-debt-restructuring | GtS5 262 + Adjudication 466 + Program 276 + TimingJudgment 444 | **真实现** |
| s6-fund-occupation | GtS6 246 + Adjudication 296 + Program 358 + RegulatoryReference 159 | **真实现** |
| s12-cpa-expert | GtS12 344 + 11 子（Branch×4/Evaluation/Program/Competence/Objectivity/Specialty/Appropriateness/ExpertReport，121~381 行） | **真实现（最丰富）** |
| s13-mgmt-expert | GtS13 330 + Branch 383 + Evaluation 330 + Program 290 | **真实现** |
| s14-accounting-estimate | GtS14 304 + 5 子（BiasIndication/Control/Environment/Program/RiskResponse，282~373） | **真实现** |
| s15-eps-roe | GtS15EpsRoe 328 + BasicEps 512 + DilutedEps 352 + Roe 432 + Program 124 + Adjudication 143 | **真实现（含计算）** |
| s20-revenue-deduction | GtS20RevenueDeduction **1106 行**单文件 | **真实现（最大单组件）** |
| s21-data-asset | GtS21DataAsset 334 + 5 子（Amortization/BasicInfo/Capitalization/CostAllocation/Program，128~509） | **真实现** |
| s32-fraud-bundle | GtS32Bundle 454 + S32_TAB_CONFIG 144 + useS32BundleState 220 | **bundle 真实现，子底稿走通用控制台** |
| s33-ann14-bundle | GtS33Bundle 407 + S33_TAB_CONFIG 112 + useS33BundleState 220 + 测试 | **bundle 真实现，子底稿走通用控制台** |
| s34-ipo-bundle | GtS34Bundle 475 + ChecklistOverview 337 + SubCheckTable 375 + S34_TAB_CONFIG 372 + useS34CrossRef 111 + useS34FormulaEngine 327 + useS34ImportExport 156 | **bundle 真实现（最成熟），子底稿走通用控制台 + 2 张公式子表试点** |
| s35-refinance-bundle | GtS35Bundle 354 + GtS35DetailTable 463 + useS35CrossRef 109 | **bundle 真实现，子底稿走通用控制台** |

**无专属顶层组件（走 `a-program-console` 通用兜底）**：S1 / S2 / S8 / S9 / S10 / S11 / S16 / S17。
- 其中 S1/S8/S9/S10/S17 另有 `s-checklist/` 目录下 13 个专属子 sheet 组件，**但未接线**（见 2.4）。
- S2 / S11 / S16 连专属子组件都没有，纯走通用程序表中控台。

证据：`audit-platform/frontend/src/components/workpaper/registry/entries/specialized.ts` 注册了 s3/s4/s5/s6/s12/s13/s14/s15/s20/s21/s32/s33/s34/s35 共 14 个 S componentType；**没有 s1/s2/s8/s9/s10/s11/s16/s17 的任何 componentType 注册**。

### 2.3 bundle 模式深度剖析（S32/S33/S34/S35）

**bundle 内部组织方式【已确认】**：每个 bundle 用可滚动 `el-tabs` 把子底稿组织成"一子底稿一 tab"，但每个 tab 内渲染的是**通用** `GtAProgramConsole`（程序表中控台），不是针对每张模板定制的组件。

证据 `GtS34Bundle.vue`（`s34-ipo-bundle/GtS34Bundle.vue` template 段）：
- tab 循环 `v-for="tab in visibleTabs"`；非 overview 的 tab 渲染 `<GtAProgramConsole :wp-id="wpIdMap[tab.wpCode]" :sheet-name="`${tab.wpCode}程序表`">`；
- 仅当 `tab.hasSubTable` 时额外渲染 `<GtS34SubCheckTable :sub-sheets="tab.subSheets">`。
- overview tab 渲染 `GtS34ChecklistOverview`（清单总览 + 适用性 + 完成进度）。

**TAB_CONFIG 登记数 vs 模板目录数对账【已确认】**：

| bundle | TAB_CONFIG 登记子底稿 | 模板目录子底稿 | 对账 |
|---|---|---|---|
| S34 | `S34_TAB_DEFS` 41 条（+overview），`S34_WITH_SUB_TABLE` 12 条含子检查表 | S34-1~S34-41（S34-0 为清单总览，S34-1-1 为 docx） | **基本对齐**；hasSubTable 子 sheet（S34-2-1/2/3-1/4-1/8-1/2/9-1/11-1/16-1/2/18-1/20-1/25-1/2/3/30-1/34-1/2）由 `GtS34SubCheckTable` 承载 |
| S32 | `S32_FRAUD_TABS` 13 条 | S32-1~S32-13 | **对齐**（13=13）；含 guidanceSheet/disclosureSheet/tipSheet 标记（S32-6/9/10 有导引+披露参考） |
| S33 | `S33_ANN14_TABS` 9 条 | S33-1~S33-9 | **对齐**（9=9）；S33-REV 走 word-template；S33-4 有 hidden 变体程序表 |
| S35 | `useS35BundleState` 的 TabDef（见 GtS35Bundle） | S35-1~S35-5 | 需看 state（未逐条核，但 CrossRef 正则 `^S35-\d+(-\d+)?$` 支持 S35-x-1 子 sheet） |

**判定**：bundle **不是空壳**，是真实现的聚合容器。但"子底稿专属渲染"**没有做**——子底稿共享通用程序表中控台。

### 2.4 真正"缺专属组件"的那一批（问题4的答案）

**（a）完全走通用兜底、无任何专属组件**：
- **S2（期初余额）、S11（利用服务机构）、S16（套期活动）** → `a-program-console`，无 s-checklist 子组件。

**（b）孤儿组件（已写专属子 sheet 但未接线）——这是最隐蔽的缺口**【已确认】：
- `s-checklist/` 目录有 13 个 .vue：S1RegulationRecordSheet(428)、S8AdjudicationSheet(293)、S9×4(Adjudication/InternalControl/LegalRegulations/ProgramDescription)、S10×3(Adjudication/EnvironmentalRegulations/InternalControl)、S17×3(NonRecurringDetail/Reconciliation/TaxImpact)。
- 它们在 `s-checklist/index.ts` 被 `export`，但 **grep 全仓确认：除 `components.d.ts`（Vue 全局自动 import 的类型声明，非真实使用）外，没有任何活动 .ts/.vue 文件 import 这些组件或 `s-checklist/index`**。
- `s-checklist/index.ts` 头注释自承："这些组件通过 GtWpRenderer 的 sheet tab 机制分发，**或在未来作为 a-program-console 内部的 embedded sheet 渲染**"——即"embedded 分发"从未落地。
- `utils/resolveProcedureSheetKey.ts`（程序表 sheet 路由）**没有任何 S 段路由**（实测 Select-String 对 S1/S9/S10/S17 零命中）。
- 结论：S1/S8/S9/S10/S17 的专属子 sheet 组件**是死代码**，实际渲染时这些底稿仍然只走通用 `a-program-console`。

> 注：`word_doc` / `a-program-console` / `audit-sheet` 是通用兜底。`overrides.json` 未出现的 S 子码（理论上不存在，因为映射表对 S1~S35 已全覆盖），会走分类服务默认推断（通常 onlyoffice-sheet / audit-sheet）。实测 S 类基本都有显式映射，无"完全无映射"的黑洞；真正问题是**映射到通用兜底 + 孤儿专属组件**。

### 2.5 S34 公式引擎 / 跨引用成熟度（问题5）

**公式引擎 `useS34FormulaEngine.ts`（327 行）= 试点，非完整**【已确认】：
- 纯函数 `sumRange/safeDivide/calcRatio/extractColumnRange` + 工厂 `createThresholdFormula/createRatioFormula/createSumFormula`。
- **硬编码公式定义仅覆盖 2 张子表**：`S34_16_1_FORMULAS`（第三方回款检查表 5 个公式）、`S34_16_2_FORMULAS`（9 个占比公式）。`S34_SHEET_FORMULA_DEFS` 映射只有 `'S34-16-1'` 和 `'S34-16-2'`。
- 文件头明确标注 "试点承载公式的两张子检查表"、接入 `formula-management-library` Task 13.2 试点（Req 24.4）。
- 其余 10 个 `hasSubTable` 底稿（S34-2/3/4/8/9/11/18/20/25/30/34）的子表公式**未定义**，工厂函数存在但无具体接入。
- 判定：**试点级**，远非 41 底稿完整覆盖。

**跨引用 `useS34CrossRef.ts`（111 行）= 仅导航，无数据联动**【已确认】：
- `isS34InternalRef` 正则 `^S34-\d+(-\d+)?$` 判断是否 S34 内部引用；内部 → 切 tab；外部 → 调 `/api/wp-index-resolve` 做全局底稿跳转。
- **纯导航**：没有取数、没有把 D4 营业收入值拉进 S34-35、没有写回。S35 的 `useS35CrossRef.ts`（109 行）同构、同样仅导航。

---

## 三、关联联动现状与缺口（用户最在意）

### 3.1 S 类与 D~N / A / B 的关联（问题6）

**【已确认】S 类与实质性底稿之间几乎没有数据级联动。** 四种可能机制逐一核验：

1. **`linked_workpapers`（映射表声明式关联）**：实测 `wp_account_mapping.json` 全部 92 条 S 条目的 `linked_workpapers` 字段**均为 `None`**（python 脚本逐条打印确认）。无声明式关联。
2. **事件订阅 `WORKPAPER_SAVED`**：grep `backend/app/services/**` 的所有 `event_bus.subscribe` —— 订阅方为 A13 聚合、ACNR 缓存失效、一致性检查、合并附注刷新等，**没有任何 S 类订阅**。S 底稿保存不会触发与 D/A/B 的联动重算。
3. **ACNR 地址引用**：ACNR catalog 里有 S34 的 addr_id（如 `S34/S34-35`，见 `backend/data/acnr/catalog_snapshots/*.json`），用于 sheet 跳转路由 `jump_route_template`，**是导航/坐标注册，不是取数联动**。
4. **取数 resolver**：S 类 componentType 未注册 D~N 那种 TB/明细取数 resolver；`useS34FormulaEngine` 只在 S34 子表内部求和，不跨底稿取数。

**具体验证"S34-35 收入核查是否关联 D4 营业收入"**【已确认 = 未关联】：
- `useS34CrossRef` 对 S34-35 只会做 tab 切换（内部）或全局跳转（如引用 D4 则跳 D4 页面），**不读取 D4 的营业收入数值**。
- S34-35 模板是纯程序表（99×13），`S34_SHEET_FORMULA_DEFS` 不含 S34-35，无任何自动取数。
- `linked_workpapers` 为 None，无声明把 S34-35 绑到 D4。

**已存在的"关联"实例仅限弱形态**：
- bundle 内 tab 间跳转（`handleCrossRefClick` 内部分流）。
- 对外部底稿的**超链接式导航**（点 chip → `/api/wp-index-resolve` → 跳对应 wp 页面）。
- 法规溯源展示（regRefMap，S34 每个专项顶部显示证监会/沪深北条文，`s34_checklist_service.py:S34_CHECKLIST_DATA`）——是元数据展示，不是底稿联动。

> 对比：D~N 循环有 `cross_wp_references`（CCR chip）、TB 回写发布门、审定表联动、公式推送引擎等真实数据链。S 类**不接入 trial_balance 回写**（archived design §1.1 明确"S 类无审定表回写"），也**不在 cross_wp_references 的数据流类别里**建立到 D~N 的取数边。

### 3.2 风险导向（问题7）

**【已确认】S 类的"适用性/完成度"由"底稿是否生成"驱动，未接 B 循环风险结果。**

S34 清单适用性逻辑 `s34_checklist_service.py:get_s34_checklist`：
```
查询 wp_index 中该项目 S34-* 底稿 → 有 wp_id 则 applicability="applicable"，无则 "not_applicable"
status 由 wp_index.status 映射（_wp_status_to_completion：draft_complete/review_passed/archived→completed，in_progress→in_progress，else not_started）
```
即：**适用性 = "底稿有没有被生成"，而不是"B 循环识别的风险是否指向该事项"**。没有从 `risk_for_cycle` / B 风险评估结论驱动 S 类事项的"应做/可免"判断。`CYCLE-CROSS-REFERENCE.md:283` 明确"不要为 S 类注册 risk_for_cycle/control_test_result_for_cycle（S 不对应单一风险）"——这是设计取舍，但也意味着风险导向在 S 类**未落地到裁剪**。

### 3.3 底稿裁剪（问题8）

**【已确认】声明层有 `applicable_when`，但执行层双向断裂。**

- **声明**：`wp_account_mapping.json` 实测 S32-* / S33-* = `{'business_category': ['ipo','listed','neeq']}`，S34-* = `+'refinancing'`，S35-* = `['refinancing']`。S1~S21 无 applicable_when（全项目适用）。bundle 父码 S32/S34/S35 本身 applicable_when=None。
- **生成执行断裂**：`wp_generation_matching.py:match_workpapers` 只认 `account_codes` / `trigger=must_have` / `trigger=conditional + applies_when`。S32-35 子码 `trigger=None` 且用的是 `applicable_when`（dict）**不是 `applies_when`（str）**——所以 **scenario 匹配器根本不会因"这是 IPO 项目"而自动生成 S32-35**。只有 must_have=True 的 S1/S2/S3/S8/S14/S20 会无条件生成。
- **前端渲染断裂**：`useAProgramData.ts:isNotApplicable` 只处理 `applicableWhen === 'consolidated'`（合并审计场景），**不解析 `business_category` dict**。所以即便后端把 applicable_when 透传，前端也不会据此灰显 S32-35。
- **存在但分散的 business_category 判定**：D4/F2 等循环有自己的 IPO 可见性判定（`useD4CrossSheet.ts:ipoGroupVisible`、`useF2SpecialFormData.ts:isIpoProject`、`useF2InventorySpecialRegistration` 的 `IPO_CATEGORIES`），但**这些是各底稿各自实现、未统一，且 S bundle 未接入**。
- archived `s-cycle-workpapers/design.md:388` 有 `evaluateApplicability(wpCode, project)` 的设计，tasks.md Task 21 标 `[x]`"实现 S32~S35 applicable_when 评估逻辑"，但**现网前端 grep 不到统一 evaluateApplicability 的 S 实现**——存在"归档标完成、实际未在当前代码落地"的疑点【部分未能验证：无法确认该 Task 的产物是否曾存在后被重构移除】。

### 3.4 委派人员（问题9）

**【已确认】委派是循环级，不是底稿级。**
- `assignment_service.py` 的分派单位是 `assigned_cycles`（如 `["S"]` 或 `["D","E"]`），通知内容 `负责循环：{cycles}`（`:284`）。
- 没有"把 S34-16 单独派给某审计员"的字段/逻辑。S 类底稿**能**被覆盖（只要项目分派了 S 循环给某人），但**粒度到循环为止**。
- 进度/复核：S 底稿的 status 走通用 wp_index.status（draft/in_progress/review_passed/archived），bundle 的进度仪表盘读的就是这个。所以 S 纳入了通用进度/复核流程，但没有 S 专属的复核链。

### 3.5 S 类关联关系权威定义表（问题10）

**【部分确认】存在若干元数据定义源，但没有一张"S↔其他循环取数关联"的权威联动表：**
- `backend/data/wp_system_map.json` 有 `S34_csrc` 节点列出 S34-1~S34-41 全序列 + 描述链（证监会核查事项编排），是**展示用导览图**，非取数边。
- `s34_checklist_service.py:S34_CHECKLIST_DATA`（41 条）是 regRef（证监会/沪深北条文）权威映射，**法规溯源**而非底稿联动。
- archived `_archive/10-A~S-workpaper-all-cycles-complete/CYCLE-CROSS-REFERENCE.md` 有跨循环约定（含"S 各底稿结论→A17 ch15 其他特殊考虑汇总"的下游依赖声明），但这是**文档级约定，未见代码实现**。
- archived `_archive/05-business-features/s34-ipo-review-bundle/s34_structure_reference.md` 是 S34 结构参考（分组表 + sheet 清单 + regRef），bundle 的 TAB_CONFIG 由它生成。
- grep `linkage` / `regRef` / 关联：S34 的 regRef 是法规条文，`linkage_facade_service` 等联动设施服务于 D~N/报表/附注，**S 类未接入**。

---

## 四、差距总结

### 4.1 六维现状打分表（每个 S componentType）

评级：✅ 完整 / 🟡 部分 / ❌ 缺失。"子底稿覆盖"对 bundle 指"子底稿是否有专属渲染"（非"是否有 tab"）。

| componentType / 底稿 | 组件实现深度 | 子底稿覆盖 | 关联联动 | 风险导向 | 裁剪 | 委派 | 优先级 |
|---|---|---|---|---|---|---|---|
| s3-policy-change (S3) | ✅ | n/a | ❌ | ❌ | 🟡(全项目适用) | 🟡(循环级) | 中 |
| s4-nonmonetary-exchange (S4) | ✅ | n/a | ❌ | ❌ | 🟡 | 🟡 | 低 |
| s5-debt-restructuring (S5) | ✅ | n/a | ❌ | ❌ | 🟡 | 🟡 | 低 |
| s6-fund-occupation (S6) | ✅ | n/a | ❌(宜关联关联方/大股东) | ❌ | 🟡 | 🟡 | 中 |
| s12-cpa-expert (S12) | ✅ | n/a | ❌ | ❌ | 🟡 | 🟡 | 低 |
| s13-mgmt-expert (S13) | ✅ | n/a | ❌ | ❌ | 🟡 | 🟡 | 低 |
| s14-accounting-estimate (S14) | ✅ | n/a | ❌(宜关联减值/估计类D~N) | 🟡 | 🟡 | 🟡 | 中 |
| s15-eps-roe (S15) | ✅(含计算) | n/a | ❌(宜关联净利润/净资产/股本M2) | ❌ | 🟡 | 🟡 | **高** |
| s20-revenue-deduction (S20) | ✅ | n/a | ❌(宜关联D4营收) | ❌ | 🟡 | 🟡 | **高** |
| s21-data-asset (S21) | ✅ | n/a | ❌(宜关联I/无形) | ❌ | 🟡 | 🟡 | 中 |
| s32-fraud-bundle (S32) | ✅(容器) | 🟡(通用控制台,无专属) | ❌ | ❌ | 🟡(声明有/执行断) | 🟡 | 中 |
| s33-ann14-bundle (S33) | ✅(容器) | 🟡 | ❌(S33-5宜读D4/F5) | ❌ | 🟡 | 🟡 | 中 |
| s34-ipo-bundle (S34) | ✅(最成熟) | 🟡(通用控制台+2张公式试点) | ❌(纯导航) | 🟡(清单适用性) | 🟡 | 🟡 | **高** |
| s35-refinance-bundle (S35) | ✅(容器) | 🟡 | ❌(纯导航) | ❌ | 🟡 | 🟡 | 中 |
| **S1** (a-program-console) | ❌(通用兜底,s-checklist孤儿) | ❌ | ❌ | ❌ | ✅(全项目/must_have) | 🟡 | **高** |
| **S8** (a-program-console) | ❌(通用,s-checklist孤儿) | ❌ | ❌ | ❌ | ✅(must_have) | 🟡 | 中 |
| **S9** (a-program-console) | ❌(通用,s-checklist孤儿) | ❌ | ❌ | ❌ | 🟡 | 🟡 | 中 |
| **S10** (a-program-console) | ❌(通用,s-checklist孤儿) | ❌ | ❌ | ❌ | 🟡 | 🟡 | 低 |
| **S17** (a-program-console,.xls) | ❌(通用,s-checklist孤儿) | ❌ | ❌(宜读利润表/非经常损益) | ❌ | 🟡 | 🟡 | **高** |
| **S2 / S11 / S16** (a-program-console) | ❌(通用,无任何专属) | ❌ | ❌ | ❌ | 🟡 | 🟡 | 中(S2 must_have) |

**最该优先补**（综合"用户诉求=联动 + 实现缺口"）：
1. **S20 / S15 / S17**：单项但本应与 D4 营收 / 利润表净利润·净资产 / 非经常性损益强联动，且 S17 还是 .xls + 孤儿组件双重缺口。
2. **S34 bundle**：IPO 核心、已最成熟，补"子底稿公式完整化 + S34-35↔D4 等取数联动"收益最大。
3. **S1 + s-checklist 孤儿接线**：把已写未接的 13 个组件接上，低成本消除"看着有、实际没用"的假象。
4. **裁剪执行链打通**：把 `applicable_when(business_category)` 从声明接到生成匹配器 + 前端灰显，让 IPO/再融资项目自动带出 S32-35、普通年审自动隐藏。

### 4.2 "还没做专属组件"前提 vs 现状（问题12 的最终判断）

**基于证据的判断：三者皆有，但权重不同：**

- **(A) bundle 是空壳？ —— 否。** S32/S33/S34/S35 bundle 是真实现的聚合容器（tab + 清单 + 法规溯源 + 进度）。但**子底稿没有专属渲染**，统一用通用 `GtAProgramConsole`。所以更准确的描述是"bundle 外壳做好了，子底稿专属化没做"。
- **(B) 需要把 skip 的子底稿拆成独立组件？ —— 不必全拆，但需按模板补"专属子表/公式"。** 当前子底稿靠通用程序表中控台能用，但 S34-16 式的"公式子检查表"只做了 2 张试点；其余含 hasSubTable 的底稿、以及宽表型（S34-35 收入核查）缺按模板定制的计算/勾稽。方向应是"在 bundle 内按模板逻辑补专属子表 + 公式引擎完整化"，而非把每个子码拆成顶层 componentType（那会破坏 bundle 聚合价值）。
- **(C) 某些单项底稿才真正缺组件？ —— 是，这是最明确的缺口。** S2/S11/S16 纯走通用兜底；S1/S8/S9/S10/S17 的专属子组件是**孤儿（已写未接线）**。这批是"真正缺专属组件"的实锤。

**一句话结论给用户**：专属组件的"主体"大部分已存在（单项 10 个 + bundle 4 个都是真实现），真正的欠账是：① 一批单项底稿（S1/S2/S8/S9/S10/S11/S16/S17）走通用兜底、且部分专属子组件写了没接线；② bundle 子底稿缺按模板的专属子表/公式（S34 公式引擎仅 2 张试点）；③ **全类普遍缺"关联联动/风险导向/裁剪执行/底稿级委派"**——这正是用户最强调的"串起来"，恰恰是现状最薄弱处。

---

## 五、建议（仅建议，未实施任何修改）

按"投入产出 + 用户诉求（关联联动优先）"排序：

### P0 — 打通裁剪执行链（低成本、高用户感知）
1. **让 `applicable_when(business_category)` 真正生效**：
   - 生成侧：在 `wp_generation_matching.py:match_workpapers` 增加对 `applicable_when.business_category` 的判定分支（读项目 business_category/project_type），使 IPO/再融资项目自动带出 S32-35、普通年审不带出。
   - 渲染侧：把 `useAProgramData.ts:isNotApplicable` 从只认 `'consolidated'` 扩展为解析 `business_category` dict（复用 D4/F2 已有的 `IPO_CATEGORIES` 口径，收敛为单一工具函数，避免各底稿各写一份）。
   - 证据依据：声明已在映射表（3.3），只差执行两端接线。

2. **接线 s-checklist 孤儿组件**：在 `GtAProgramConsole` 的 sheet 分发层（或 `resolveProcedureSheetKey.ts` 增加 S 段）把 S1/S8/S9/S10/S17 的专属子 sheet 接上，消除死代码。先确认这批组件字段绑定是否仍与模板一致（13 个组件已存在，接线成本远低于重写）。

### P1 — 关联联动（用户最在意，收益最大）
3. **建立 S→D~N 取数边**：优先 S20↔D4 营收、S15↔利润表净利润/M2 股本/净资产、S17↔利润表非经常性损益、S33-5↔D4/F5 收入毛利。机制建议复用已成熟的 ACNR addr_id 引用 + 公式推送/resolver，而非前端拼坐标。给这些 S 底稿在 `wp_account_mapping.json` 补 `linked_workpapers`，并注册取数 resolver。
4. **S34 公式引擎完整化**：把 `useS34FormulaEngine` 从 2 张试点扩展到全部 `hasSubTable` 子表（工厂函数 createRatioFormula/createSumFormula/createThresholdFormula 已就位，缺的是逐表 FORMULA 定义）。

### P2 — 风险导向与委派
5. **风险导向裁剪**：让 B 循环风险评估结论（舞弊风险高 → S32 适用、特定事项风险 → 对应 S34 专项适用）驱动 S 清单的"建议适用/可免"，而非仅看"底稿是否已生成"。
6. **底稿级委派（可选）**：若业务需要，把 `assignment_service` 的 `assigned_cycles` 扩展为支持 wp_code 粒度（或在 S bundle 内按 tab 显示负责人/复核状态）。

### 实施前必做（基于本仓库铁律）
- 改动前先 spec 三件套（跨前后端 + 3+ 组件，符合"改动前先 spec"门槛）。
- 设计阶段做"现状 grep 确认"：确认 applicable_when 的 archived Task 21 产物是否真的不存在（本调查未能验证其历史产物，实施者需现算核对）。
- 任何 TB 相关联动须走显式发布门（S 类历来不回写 TB，新增联动若涉及取数而非回写则不受此限，但需确认方向）。

---

## 六、已确认 / 未能验证 清单

**已确认（有文件+行号/实测证据）：**
- S 模板文件清册与格式差异（文件系统实测 + openpyxl 读 sheet dims）。
- componentType 映射全貌（`wp_code_overrides.json:1370-1497`）。
- 单项 10 个 + bundle 4 个为真实现（组件行数 + registry 注册 + template 结构）。
- bundle 子底稿走通用 `GtAProgramConsole`（`GtS34Bundle.vue` template）。
- S34 公式引擎仅 2 张子表试点（`useS34FormulaEngine.ts:S34_SHEET_FORMULA_DEFS`）。
- S34/S35 跨引用仅导航无取数（`useS34CrossRef.ts` / `useS35CrossRef.ts`）。
- S 类 `linked_workpapers` 全 None（python 逐条打印 92 条）。
- 无 S 类 WORKPAPER_SAVED 订阅（grep subscribe）。
- `applicable_when` 声明存在但生成匹配器与前端灰显均不识别 business_category dict（`wp_generation_matching.py` / `useAProgramData.ts`）。
- s-checklist 13 组件孤儿（grep import 零命中，index.ts 头注释自述未接线，resolveProcedureSheetKey 无 S 段）。
- 委派为循环级（`assignment_service.py:assigned_cycles`）。
- S34 清单适用性=底稿生成驱动（`s34_checklist_service.py:get_s34_checklist`）。

**未能验证（需实施者现算核对）：**
- archived `s-cycle-workpapers/tasks.md` Task 21"实现 applicable_when 评估逻辑"标 [x]，但当前代码未见统一 `evaluateApplicability` 的 S 实现——无法判断是"从未实现/假绿"还是"曾实现后被重构移除"。
- S35 bundle 的 TabDef 子底稿数未逐条与 S35-1~5 模板对账（CrossRef 正则支持 S35-x-1，但未读 `useS35BundleState` 确认 tab 条数）。
- S13 在 overrides 是 `s13-mgmt-expert`，与 archived design 计划的 a-program-console 不一致——以现行 overrides 为准，但两者分歧原因未追。
- 各单项 S 组件内部是否已有隐性取数（本调查以 crossref/linked/事件三路判定为"无联动"，未逐个通读 10 个单项组件的 onMounted 取数逻辑，个别可能有局部取数未覆盖到）。
