# Design Document

## Overview

本设计把函证枢纽做成**底稿层（Hub_Workbook 多 sheet 编制）+ 中心层（Confirmation_Center 台账）双层并存、双向联动**的闭环。

P0 已完成（基线）：`confirmation-hub` 进入 `HTML_RENDERER_ROUTE_SET`（不进 registry）、`WorkpaperEditor` 移除整体重定向 + 标题栏 Center_Entry。本设计在此基线上补齐 **Hub_Sheet 呈现治理**（遗留 sheet / 编码冲突 / 异构枢纽）与 **四条联动链**（Sync_To_Center、Reply_Backflow、Unreplied_Pull、可追溯），并以 Linkage_Matrix 保证七枢纽一致。

**核心发现：七枢纽远非同构**（下表为 postgres + wp_code_overrides 实证，非假设），因此设计的第一性约束是「按实际 sheet 名与实际 override 驱动，不按 X0-N 命名假设推导」。

## Architecture

```
┌─────────────────────── 底稿层（Hub_Workbook）────────────────────────┐
│ WorkpaperEditor ──(useHtmlRenderer: confirmation-hub ∈ ROUTE_SET)──▶ │
│   GtWpRenderer ──per-sheet componentType 分发──▶                     │
│     b-index / a-program-console / confirmation-summary /             │
│     confirmation-entity-verify / -followup / -diff-reconcile /       │
│     -diff-checklist / -alternative-* / -reliability / -fraud-risk    │
│                                                                      │
│   [Center_Entry 按钮] ──────────────────────────────┐                │
└─────────────────────────────────────────────────────┼────────────────┘
                    ▲                                 │
        Reply_Backflow (R4)                  导航 (R2) │
   confirmation:received / 持久化读取                   ▼
┌─────────────────────── 中心层（Confirmation_Center）──────────────────┐
│ ConfirmationHub.vue ── confirmation 表（台账真源投影）                │
│   状态机 pending→sent→returned→matched|discrepancy                   │
└──────────────────────────────────────────────────────────────────────┘
                    ▲
        Sync_To_Center (R3)  syncHubFromSummary（幂等 upsert + 状态推进）
                    │
        Summary_Sheet（X0-1，confirmation-v1 编制真源）
                    │
        Unreplied_Pull (R5)  importFromSummary
                    ▼
        Alternative_Sheet（X0-5 / X0-6）
```

**数据真源分层（不变）**：Summary_Sheet = 编制真源（confirmation-v1）；`confirmation` 表 = 项目级台账投影 + 回函状态真源；科目明细底稿 = 消费方。本设计不改这一分层。

### 关键决策

**决策 1：Hub_Sheet 呈现治理走 sheet 级 skip override，不改 render 策略**

E0 实测 20 个 sheet，其中 9 张是遗留/备份/参考（`函证程序表-原版本备份`、`函证结果汇总表E0-1（原）`、`函证结果汇总表E0-1 (备份)`、`函证结果汇总表-旧版`、`货币资金及借款函证结果汇总表-旧版`、`核实被函证单位信息F1-10-原`、`邮件传真回函核对记录F1-12`、`参考用-往来函证程序`、`回函情况汇编`）。P0 修复后这些会**全部变成 tab**，比 F0 严重得多。

治理方式：按 **sheet_name 精确 key** 写入 `wp_code_overrides.json` 的 `"skip"`（平台既有机制，precedent：`"长期应付职工薪酬实质性程序表 L2A": "skip"`）。**不按编码 skip**（会误伤真实 sheet），**不改 render 策略过滤逻辑**（影响面大）。

**决策 2：跨枢纽编码污染按 sheet_name override 纠正，不改源模板**

实测污染：G0 含 `函证程序舞弊风险评价表F0-8`（F0 编码）、L0 含 `函证程序表F0A`（F0 编码）。sheet 级 wp_code 解析取尾码 → 得 F0-8 / F0A → 恰好映射到正确的组件类型（fraud-risk / a-program-console），**功能不坏但索引号错**（`activeSheetIndexNo` 会显示 F0-8 而非 G0-8）。

治理：按 sheet_name 精确 override 到正确 componentType，索引号偏差登记为已知偏差（源模板复制遗留，不改源 xlsx）。

**决策 3：G0-3 编码冲突必须修（真 bug）**

G0 有两张 sheet 尾码都解析为 `G0-3`：`跟函函证过程控制G0-3`（应 followup）与 `函证差异核对表G0-3（证券投资）`（应 diff-securities）。后者尾部是「（证券投资）」→ 尾码正则匹配不到 → 落 class_code 派生或错配。且 `G0-3S → confirmation-diff-securities` 这条 override **是按编码 key 写的，sheet 名里不存在 G0-3S**，属死配置。

治理：给 `函证差异核对表G0-3（证券投资）` 加 **sheet_name 精确 override** → `confirmation-diff-securities`；`G0-3S` 编码 key 保留（无害）或标注。

**决策 4：E0 重建为 confirmation-\* 结构（用户拍板 B 方案），映射依源模板实证不臆造**

E0 当前 override 是 `E0-1~E0-5 → d-form-table`（通用表格），故 Sync_To_Center / Reply_Backflow 无承载 sheet。用户决定**本 spec 内一并重建**（理由：否则后续仍要做，且银行函证是最高频函证场景）。

**可行性三项实证（决定性）**：

1. **E0-1 本就是标准函证结果汇总表**（源模板 `函证结果汇总表E0-1`，54×35）。表头三段与其他枢纽 X0-1 同构：
   - 发函信息：序号 / 询证函索引号 / 被询证单位名称 / 账户或交易 / 账号或理财产品名称 / 发函金额（原币）/ 币种 / 汇率 / 发函金额（本位币）/ 函证方式 / 发函日期 / 发函单号 / 收件地址 / 地址核查是否一致
   - 收到回函：是否收到回函 / 回函方式 / 是否相符 / 回函日期 / 回函快递单号 / 回函发出地址 / 发函地址与回函地址是否一致
   - 回函金额确认：回函金额
   - 预置行按**账户类型**分 5 类：银行存款 / 其他货币资金 / 短期借款 / 应付票据 / 理财产品
2. **`accountTabs` 是从行数据 `account_type` 动态派生**（`useConfirmationData` 去重排序），**非硬编码**→ E0 五类账户天然支持，`confirmation-summary` 组件与 confirmation-v1 数据模型**无需任何改动**。
3. **迁移风险可忽略**：postgres 实证 E0 系列 `checklist_responses` 行数 = E0(1) / E0-1~E0-5(各 0)，即**几乎无既有编制数据**。

**E0-3 ~ E0-6 定位为发函前清单（上游），不改其 componentType**：源模板实证 E0-3 是「货币资金发函信息表」（所属科目 / 开户银行 / **是否函证** / 账户名称 / 银行账号 / 币种 / 利率 / 账户类型 / 账户余额（原币）/ 是否资金归集 / 起止日期 / **是否存在冻结担保或使用限制** / 备注），E0-4 是借款清单（借款人 / 借款账号 / 余额 / 借款日期 / 到期日 / 利率 / 抵质押品担保人 / 借款类型 / 期末应付利息）。这是**函证对象来源台账**而非函证过程表，保持 `d-form-table` 正确；新增能力是「清单 → E0-1 带入」（筛 `是否函证 = 是` 的行生成 Summary_Sheet 行）。

**E0 仍不适用的两项，如实登记不臆造**：
- **差异调节表**：E0 源模板无 X0-4 类差异调节 sheet（差异信息由 E0-1 的「是否相符 / 回函金额」承载）→ Linkage_Matrix 登记 `not_applicable`
- **替代程序**：E0 源模板无替代程序 sheet → `unreplied_pull` 登记 `not_applicable`（禁造 sheet）

**决策 5：Sync_To_Center 空态入口 —— 改空态视图而非改同步逻辑**

`GtConfirmationSummary` 的「同步到函证中心」按钮 `v-if="!readonly"` 本身无数据门控，看不到是因为**空态渲染"开始编制函证底稿"引导视图替换了整个 toolbar**。治理 = 在空态引导视图内保留/补上 Sync_To_Center 与 Center_Entry 入口，**不动 `handleSyncHub` / `_autoSyncAfterSave` 既有逻辑**（零回归）。

**决策 6：Unreplied_Pull 统一复用既有共用能力，STUB 桩逐套替换**

`coordination/importFromSummary.ts` 已存在且被 H05/K05/K06/L05 适配器复用（`createAlternativeConfirmationData` 工厂 + 旁挂 `importFromSummary`）。D0-6 / F0-5 / F0-6 的 STUB 桩改为同款接线，**不新造第二套跨底稿读取实现**。

**决策 7：Reply_Backflow 以持久化为准、事件为加速**

台账回函推进后：①同会话经 `confirmation:received` 即时刷新（已有）；②**跨会话必须能从持久化读到**（R4.5）——即回函结果必须落在 Summary_Sheet 可读的位置（台账 `confirmation` 表 + 底稿行的 hubId 关联），打开底稿时按 hubId 拉取台账状态刷新。手工优先：底稿行若已有审计师手工值则不覆盖（P8）。

**决策 8：路由解析治理只加 override 与「父码优先」的模板 key 推导，不改 `_SHEET_CODE_RE`**

实证解析链（`wp_render_config.py:734-743`）：`Sheet_Code_Tail override` → **`sheet_name` 精确 override** → `{wp_code}-{sheet_name}` override。故编码不在尾部的 sheet（G0 两张差异核对表以「（证券投资）」「(非证券投资)」收尾）**已有可用的精确 override 通道**，无需改正则（改正则会影响全平台 441 个 schema/所有多 sheet 底稿，风险不成比例）。

G0 未命中 sheet_ovr 时的实际落点：`_cls_code.startswith("G-")` 分支会**强制改写为 `onlyoffice-sheet`**（`wp_render_config.py:791-802`），即这两张表当前大概率呈现为 OnlyOffice 视图而非空白——具体形态属 Wave 0 待实测项，但无论哪种，`diffSecurities` 组件都是零渲染。

程序表模板 key（`_a_program.py:212-216`）：从 sheet_name 正则提取，不校验循环前缀。治理 = **父码优先**——若提取到的 Program_Template_Code 的循环前缀 ≠ 父 wp_code 的循环前缀，先试 `{wp_code}A`；`get_template` 命中则用它，未命中则回退原提取值（保持既有 xlsx 提取兜底，零回归）。这一改动同时修掉 L0 的 `F0A` 劫持，且对所有「sheet 名编码与父码不同循环」的底稿普遍生效。

**G0-4（非证券投资）差异核对表本 spec 只保证「渲染成 `confirmation-diff-reconcile` 不落兜底」**；其源模板的「持股比例 / 投资金额 / 投资条款 × 账面·回函·差异」三维结构 `diffReconcile` 无法承载，属 `g0-investment-diff-model` spec 范围（本 spec 不臆造三维模型）。

## Components and Interfaces

### 既有组件（复用，不新造）

| 组件/模块 | 职责 | 本设计动作 |
|---|---|---|
| `WorkpaperEditor.vue` | 底稿编辑器宿主 | 已移除重定向 + Center_Entry（P0 完成）；本设计不再改 |
| `GtWpRenderer.vue` | per-sheet componentType 分发 | 不改 |
| `htmlRendererRegistry.ts` | 路由集合 + registry | 已加 `confirmation-hub` 到 ROUTE_SET（P0）；本设计不再改 |
| `GtConfirmationSummary.vue` | X0-1 编制 + Sync_To_Center | 仅补空态入口（决策 5） |
| `coordination/syncHubFromSummary.ts` | 幂等 upsert + 状态推进 | 不改逻辑；仅确认 hubId 回写路径 |
| `coordination/importFromSummary.ts` | 未回函带入共用能力 | 复用 |
| `coordination/emitConfirmationCompleted.ts` | 科目明细「已函证」批量回写 | 复用 |
| `ConfirmationHub.vue` | 台账 CRUD + 状态机 | 仅补「跳回来源底稿」入口（R2.4） |
| `wp_code_overrides.json` | wp_code/sheet_name → componentType | 加 skip 与 sheet_name 精确 override（决策 1/2/3/8） |
| `wp_render_strategies/_a_program.py` | 程序表渲染 + 模板 key 提取 | 加「父码优先」模板 key 推导（决策 8），保留 xlsx 回退 |
| `diffSecurities/`（G0 特有，344 行） | 证券投资差异核对 | 不改结构，仅由 override 使其首次可达 |

### 新增/改造接口

**`confirmationLinkageMatrix.ts`（新增，纯数据 + 纯函数）**

```ts
export type LinkageCapability =
  | 'sync_to_center' | 'reply_backflow' | 'unreplied_pull' | 'center_entry'

export type CapabilityState = 'implemented' | 'stub' | 'missing' | 'not_applicable'

export interface HubCycleSpec {
  cycle: 'D0' | 'E0' | 'F0' | 'G0' | 'H0' | 'K0' | 'L0'
  summarySheet: string | null        // X0-1 sheet_name，E0 为 null
  alternativeSheets: string[]        // 实际 sheet_name（0~2 张）
  capabilities: Record<LinkageCapability, CapabilityState>
  notApplicableReason?: string       // not_applicable 必须给依据
}

/** 覆盖守卫用：列出「应实现但未实现」的 (cycle, capability) */
export function findLinkageGaps(matrix: HubCycleSpec[]): Array<{
  cycle: string; capability: LinkageCapability; state: CapabilityState
}>
```

**`ConfirmationHub.vue` 新增来源底稿回跳**

```ts
/** 台账行 → 来源 Hub_Workbook 的 Summary_Sheet（R2.4/R2.5） */
function jumpToSourceSummarySheet(row: ConfirmationRecord): void
// source_wp_code（如 'F0'）→ ACNR/wp-id-by-code 解析 wp_id
//   → router.push({ name:'WorkpaperEditor', params:{projectId, wpId}, query:{ sheet: summarySheetName } })
// 解析失败 → ElMessage 明确提示"该底稿在本项目未生成"，不静默跳底稿目录
```

**程序表模板 key 父码优先（`_a_program.py`，决策 8）**

```python
# 现状：_sheet_code 仅按 sheet_name 正则提取（L0 的「函证程序表F0A」→ "F0A"）
# 治理后（纯函数化便于单测）：
def resolve_program_template_code(sheet_name: str, wp_code: str) -> str:
    """提取 sheet 级程序表编码；若其循环前缀与父 wp_code 不同循环，
    优先尝试 f"{wp_code}A"（get_template 命中才采用），否则回退提取值。"""
# 断言：("函证程序表F0A", "L0") -> "L0A"（L0A 模板存在）
#       ("销售与收款循环审计程序表D4A", "D4") -> "D4A"（同循环不变）
#       ("函证程序表F0A", "F0") -> "F0A"（父码即 F0，不变）
```

**Alternative_Sheet STUB 替换（D0-6 / F0-5 / F0-6 / K0-5）**

```ts
// 替换前（STUB）：ElMessage.info('从 X0-1 带入功能待跨底稿引用 API 接入后启用')
// 替换后（对齐 K06/L05 proven 范式）：
async function handleImportFromSummary() {
  const count = await data.importFromSummary()   // 适配器旁挂，内部走 coordination/importFromSummary
  if (count > 0) ElMessage.success(`已从 ${SUMMARY_CODE} 带入 ${count} 个未回函被函证单位`)
  else ElMessage.info('无未回函项目')
}
```

## Data Models

### Linkage_Matrix（实证基线，design 核心数据表）

sheet 名取自 `workpaper_sheet_classification`；componentType 取自 `wp_code_overrides.json`；能力状态取自代码实证。

| 枢纽 | sheets | Summary_Sheet | Alternative_Sheet(s) | Sync_To_Center | Unreplied_Pull | 结构备注 |
|---|---|---|---|---|---|---|
| **D0** 销售/应收 | 11 | 函证结果汇总表D0-1 | 合同负债及销售替代程序D0-5、应收及销售替代程序D0-6 | implemented（共享组件） | D0-5 implemented / **D0-6 stub** | 无 `D0A` override（程序表靠 class_code 派生，需核实） |
| **E0** 货币资金/借款 | **20** | 函证结果汇总表E0-1（**重建后**） | **无**（源模板确无） | **implemented（决策 4 重建后）** | **not_applicable**（无替代程序 sheet） | 现状 E0-1~E0-5 → `d-form-table`；重建目标见下「E0 重建映射表」；**7 张遗留/备份 sheet 待 skip**；E0-5 编码在两张 sheet 上重复（发函记录表 / 银行函证其他信息核对表） |
| **F0** 采购/存货 | 11 | 函证结果汇总表F0-1 | 预付及采购替代程序F0-5、应付及采购替代程序F0-6 | implemented | **F0-5 stub / F0-6 stub** | P0 实测基线（12 tab 含合成「完整Excel」） |
| **G0** 投资 | 10 | 函证结果汇总表G0-1 | 替代程序检查表G0-6 | implemented | G0-6 implemented（`pullFromG01`） | **G0-3 编码冲突**（跟函控制 vs 证券投资差异核对）；含 `函证程序舞弊风险评价表F0-8` 污染；无 X0-8 编码 |
| **H0** 固定资产 | 9 | 函证结果汇总表H0-1 | 替代程序H0-5 | implemented | H0-5 implemented | 编码偏移：舞弊=H0-7、可靠性=H0-6、差异=H0-4 |
| **K0** 其他应收/应付 | 11 | 函证结果汇总表K0-1 | 其他应收款替代程序K0-5、其他应付款替代程序K0-6 | implemented | K0-6 implemented / **K0-5 missing 入口** | 含 `GT_Custom` 占位 sheet |
| **L0** 长期应付 | 10 | 函证结果汇总表L0-1 | 长期应付款替代程序L0-5 | implemented | L0-5 implemented | 含 `函证程序表F0A` 污染；编码偏移：舞弊=L0-7、可靠性=L0-6 |

### E0 重建映射表（决策 4 落地对象）

sheet 名取自源模板 `E\E0 货币资金 - 函证（Leap应对措施-函证）.xlsx` 与分类表（一致）。

| sheet_name | 现 componentType | 目标 componentType | 依据 |
|---|---|---|---|
| 底稿目录 | b-index | 不变 | — |
| 函证程序表E0A | （无 override，class_code `A-程序表` 派生） | `a-program-console`（显式登记） | 与 F0A/G0A/H0A 一致 |
| 函证结果汇总表E0-1 | `d-form-table` | **`confirmation-summary`** | 源模板三段 21 列与其他 X0-1 同构；accountTabs 动态派生支持 5 类账户 |
| 核实被函证单位信息E0-2 | `d-form-table` | **`confirmation-entity-verify`** | 与其他枢纽 X0-2 同名同义 |
| 货币资金发函记录表E0-3 | `d-form-table` | 不变（发函前清单，上游） | 源模板是账户台账非函证过程表 |
| 借款发函记录表E0-4 | `d-form-table` | 不变（同上） | 同上 |
| 应付银行承兑汇票发函记录表E0-5 | `d-form-table` | 不变（同上） | 同上 |
| 理财产品发函记录表E0-6 | （无 override） | 不变（`d-form-table` 显式登记） | 同上 |
| 银行函证其他信息核对表E0-5 | （编码与上面 E0-5 冲突） | 按 sheet_name 精确 override → `d-form-table` | 消除 E0-5 双 sheet 编码冲突（同决策 3 手法） |
| 跟函函证过程控制E0-7 | （无 override） | **`confirmation-followup`** | 与其他枢纽 X0-3 跟函控制同义 |
| 函证程序舞弊风险评价表E0-8 | `confirmation-fraud-risk` | 不变 | 已正确 |
| 邮件传真回函核对记录F1-12 | （无 override） | **`confirmation-reliability`** | E0 无 X0-7 可靠性 sheet，该表即回函可靠性核对（借 F1-12 编码） |
| 回函情况汇编 | （无 override） | 不变（保留渲染） | 命名无遗留标记，辅助汇编视图 |

**新增能力**：E0-3 ~ E0-6 清单 → E0-1 带入（筛 `是否函证 = 是`，生成 Summary_Sheet 行并按品种置 `account_type` 为 银行存款 / 短期借款 / 应付票据 / 理财产品），复用「新增函证对象 / 从 Excel 导入」既有写入路径，**不新造 confirmation-v1 写入实现**。

**Sync_To_Center / Reply_Backflow / Center_Entry 的共享性**：Summary_Sheet 全部由**同一个** `GtConfirmationSummary` 组件渲染，故这两条链一旦修好即七枢纽同时生效（**E0 在决策 4 重建后也纳入**）；Center_Entry 在 `WorkpaperEditor` 统一提供，已全枢纽生效（P0）。**真正需逐套落地的只有 Unreplied_Pull**（4 处：D0-6 / F0-5 / F0-6 / K0-5；E0 因源模板无替代程序 sheet 不适用）。

### 呈现治理清单（决策 1/2/3 的落地对象）

| sheet_name（精确 key） | 所属 | 动作 | 依据 |
|---|---|---|---|
| 函证程序表-原版本备份 | E0 | `skip` | 备份版本 |
| 函证结果汇总表E0-1（原） | E0 | `skip` | 旧版重复 |
| 函证结果汇总表E0-1 (备份) | E0 | `skip` | 备份 |
| 函证结果汇总表-旧版 | E0 | `skip` | 旧版 |
| 货币资金及借款函证结果汇总表-旧版 | E0 | `skip` | 旧版 |
| 核实被函证单位信息F1-10-原 | E0 | `skip` | 跨底稿遗留旧版 |
| 邮件传真回函核对记录F1-12 | E0 | **保留** + override → `confirmation-reliability` | **不 skip**：E0 自身无 X0-7 可靠性 sheet（E0-7 是跟函过程控制），该表功能正是回函可靠性核对，判定为 E0 实际在用（借用 F1-12 编码），索引号偏差按决策 2 登记 |
| 参考用-往来函证程序 | E0 | `skip` | 名称显式标「参考用」，参考资料非编制底稿 |
| 回函情况汇编 | E0 | **保留**（不 skip，按 class_code 派生） | 名称无旧版/备份标记，功能为回函情况汇编（辅助视图），依「宁缺勿造：不确定不隐藏」保留 |
| GT_Custom | K0 | `skip` | 自定义占位 |
| 函证差异核对表G0-3（证券投资） | G0 | → `confirmation-diff-securities` | 决策 3（修编码冲突） |
| 函证程序舞弊风险评价表F0-8 | G0 | → `confirmation-fraud-risk` | 决策 2（污染纠正，索引号偏差登记） |
| 函证程序表F0A | L0 | → `a-program-console` + 模板 key 按父码取 `L0A`（决策 8） | 决策 2 + P0-2（L0A 模板此前永不生效） |
| 函证差异核对表G0-4(非证券投资) | G0 | → `confirmation-diff-reconcile`（先保可达） | 决策 8；三维结构留给 `g0-investment-diff-model` spec |

**注 1**：`函证差异检查表（示例）` 已有 sheet_name override → `confirmation-diff-checklist`，无需处理（D0/F0/L0 共用）。

**注 2（skip 判定依据）**：E0 全部 20 张 sheet 的 `is_real_workpaper` 均为 `True`、`exclude_from_progress` / `exclude_from_archive` / `is_static_doc` 均为 `False`（postgres 实证），**分类表本身不提供遗留标记**，故 skip 判定唯一线索是**命名显式标记**（`-原版本备份` / `（原）` / `(备份)` / `-旧版` / `-原` / `参考用-`）。凡命名无此类标记者一律保留渲染（skip 是破坏性动作：会让该 sheet 数据在编辑器内不可达）。

**注 3**：`skip` 仅影响编辑器页签呈现，不改变归档与文件内容（`exclude_from_archive` 不动），故不构成审计留痕风险。

## Correctness Properties

### Property 1: Hub_Sheet 页签集合等于分类表中未 skip 的 sheet 集合
对任一 Hub_Workbook，编辑器渲染的页签（除合成页签「完整Excel」）SHALL 与 `workpaper_sheet_classification` 中该 wp_code 下未被 `skip` 的 sheet 一一对应，不多不少。
**Validates: Requirements 1.1, 1.3**

### Property 2: workbook 级类型在路由集合内且不在渲染注册表内
`confirmation-hub` SHALL ∈ `HTML_RENDERER_ROUTE_SET` 且 SHALL ∉ `HTML_COMPONENT_TYPE_SET`。
**Validates: Requirements 1.4**

### Property 3: Hub_Workbook 不重定向
打开任一 Hub_Workbook 后路由 SHALL 仍在底稿编辑器路径，不含 Confirmation_Center 路径段。
**Validates: Requirements 1.2**

### Property 4: sheet_name 精确 override 优先于编码尾码解析
当某 sheet 同时可被 sheet_name override 与编码尾码解析命中时，结果 SHALL 取 sheet_name override（保证 G0-3 冲突与污染纠正生效）。
**Validates: Requirements 6.2, 1.3**

### Property 5: Sync_To_Center 幂等
同一批 Summary_Sheet 行重复执行 Sync_To_Center，台账中对应记录数 SHALL 不增加（按 hubId/对方+类型去重），且状态 SHALL 不回退。
**Validates: Requirements 3.1, 3.4, 9.1**

### Property 6: 空态不吞入口
Summary_Sheet 在空态（0 行）下，Sync_To_Center 入口 SHALL 可达（非只读态）。
**Validates: Requirements 3.3**

### Property 7: 只读态禁写入口
只读 / EQCR 态下 Sync_To_Center 与 Unreplied_Pull 入口 SHALL 不可用。
**Validates: Requirements 3.6**

### Property 8: Reply_Backflow 手工优先
若底稿行的目标字段已有审计师手工值，回流 SHALL NOT 覆盖该值。
**Validates: Requirements 4.4, 9.3**

### Property 9: Reply_Backflow 不依赖同会话事件
台账回函推进后关闭并重新打开 Summary_Sheet，回函状态与金额 SHALL 仍可见（经持久化读取）。
**Validates: Requirements 4.5**

### Property 10: Unreplied_Pull 去重
对同一 Summary_Sheet 重复执行 Unreplied_Pull，Alternative_Sheet 中同一被函证单位 SHALL 只存在一行。
**Validates: Requirements 5.4, 9.2**

### Property 11: Unreplied_Pull 无桩残留
所有具备 Alternative_Sheet 的枢纽 SHALL NOT 存在「待接入后启用」类提示实现。
**Validates: Requirements 5.2, 5.3**

### Property 12: Unreplied_Pull 空集合与不可读的显式反馈
无未回函项目时 SHALL 给出「无未回函项目」提示；Summary_Sheet 不可读时 SHALL 给出可理解提示且不抛未捕获异常。
**Validates: Requirements 5.5, 5.6**

### Property 13: E0 重建后 Summary_Sheet 可承载五类账户
E0-1 渲染为 `confirmation-summary` 后，当行数据含 银行存款 / 其他货币资金 / 短期借款 / 应付票据 / 理财产品 时，`accountTabs` SHALL 派生出对应的全部科目页签（验证动态派生对 E0 成立，无需硬编码）。
**Validates: Requirements 6.2, 3.1**

### Property 14: E0 清单 → E0-1 带入只取「是否函证 = 是」且去重
从 E0-3 ~ E0-6 带入 E0-1 时，SHALL 仅生成 `是否函证 = 是` 的行；重复带入同一账户/借款 SHALL NOT 产生重复行；带入行的 `account_type` SHALL 按来源品种正确置值。
**Validates: Requirements 5.4, 6.4**

### Property 15: E0 重建不臆造缺失 sheet
E0 的差异调节与替代程序能力 SHALL 登记为 `not_applicable` 且带依据，SHALL NOT 在 E0 下新建源模板不存在的 sheet。
**Validates: Requirements 6.3**

### Property 16: Linkage_Matrix 无遗漏
`findLinkageGaps(matrix)` SHALL 返回空数组（`not_applicable` 项必须带 `notApplicableReason`）。
**Validates: Requirements 6.1, 6.3, 6.5, 9.4**

### Property 17: 复用共用能力不造第二套
Unreplied_Pull 的实现 SHALL 经 `coordination/importFromSummary`；Sync_To_Center SHALL 经 `coordination/syncHubFromSummary`；科目明细回写 SHALL 经 `coordination/emitConfirmationCompleted`。
**Validates: Requirements 6.4**

### Property 18: 台账既有能力零回归
Confirmation_Center 的台账 CRUD、状态机推进、从底稿导入、批量同步、覆盖率统计 SHALL 行为不变；既有函证域测试与渲染注册表契约测试 SHALL 全绿。
**Validates: Requirements 8.1, 8.2**

### Property 19: 非 Hub 底稿路由不变
非 Hub_Workbook 底稿的编辑器路由判定 SHALL 逐字不变。
**Validates: Requirements 8.3**

### Property 20: 联动来源可追溯
经 Unreplied_Pull 带入的行 SHALL 带来源标注；已同步的 Summary_Sheet 行 SHALL 可见同步状态。
**Validates: Requirements 7.1, 7.3**

### Property 21: 每张未 skip 的 Hub_Sheet 都解析到非兜底 componentType
对七枢纽每张未 skip 的 sheet，解析结果 SHALL ∉ {`confirmation-hub`, `skip`}，且 G0 的证券投资差异核对表 SHALL = `confirmation-diff-securities`。
**Validates: Requirements 10.1, 10.2, 10.7**

### Property 22: 程序表模板 key 父码优先且可回退
`resolve_program_template_code(sheet_name, wp_code)`：循环前缀不一致且 `{wp_code}A` 有模板时 SHALL 返回 `{wp_code}A`；`{wp_code}A` 无模板时 SHALL 返回原提取值；循环前缀一致时 SHALL 逐字返回原提取值。
**Validates: Requirements 10.4, 10.5, 10.9**

### Property 23: 死配置不被依赖
`G0-3S` 类「sheet_name 中不存在该编码」的 override key SHALL 不影响任何 sheet 的解析结果（移除或保留均不改变输出）。
**Validates: Requirements 10.3**

### Property 24: Index_Code_Map 完整且偏差有据
Index_Code_Map SHALL 覆盖七枢纽全部未 skip 的 sheet；凡 Sheet_Code_Tail ≠ 源模板真实索引号者 SHALL 带偏差原因，且 SHALL NOT 通过改源 xlsx 消除。
**Validates: Requirements 10.6, 10.8**

## Error Handling

| 场景 | 处理 |
|---|---|
| Sync_To_Center 网络/权限失败 | 提示失败原因，底稿内容不丢；不清空 hubId |
| Sync_To_Center 无可同步行 | 明确提示「暂无需同步的行」，非错误 |
| Unreplied_Pull 读不到 Summary_Sheet | 提示「未找到 X0-1 或尚未编制」，不抛异常（fail-open） |
| Unreplied_Pull 无未回函项目 | 提示「无未回函项目」 |
| Center_Entry / 回跳目标底稿未实例化 | 明确提示「该底稿在本项目未生成」，不跳底稿目录 |
| `confirmations/match-queue` 500（既有缺陷） | 台账页面局部降级，SHALL NOT 阻断底稿层能力（范围外，不修） |
| 命名无遗留标记的 sheet | 一律保留渲染（不 skip）；skip 是破坏性动作（数据在编辑器内不可达），仅对命名显式标注 备份/原/旧版/参考用 的 sheet 执行 |

## Testing Strategy

- **契约测试**：`confirmation-hub` 路由集合/注册表归属（P2）；sheet_name override 优先级（P4）；Linkage_Matrix 覆盖守卫（P13）；共用能力复用守卫（P14，grep 式断言 STUB 文案不存在 → P11）
- **属性测试（fast-check）**：Sync_To_Center 幂等（P5）、Unreplied_Pull 去重（P10）、手工优先（P8）
- **单元测试**：`findLinkageGaps`、空态入口可达（P6）、只读门控（P7）、空集合/不可读反馈（P12）
- **零回归门**：函证域全量前端测试（当前 39 文件 / 710 例）+ `htmlRendererRegistry.spec` + `useEditorMode.spec` + `componentTypeContract.spec` 全绿；改动文件 `get_diagnostics` 清 + Vite transform 200
- **Playwright（每枢纽一次）**：打开 Hub_Workbook → 页签集合符合 Property 1 → 逐 tab 无占位/无加载失败 → Center_Entry 跳转 → Summary_Sheet 空态入口可见 → Alternative_Sheet 带入按钮非桩提示
- **live round-trip（避污染范式）**：对真实项目做 Sync_To_Center 时，采用「先备份受影响 `confirmation` 行 → HTTP 同步 → 断言 → 精确恢复 + `RESTORED_IDENTICAL` 断言」，不留测试数据

## Migration / Phasing

| 阶段 | 内容 | 可回退性 |
|---|---|---|
| **M0** | Wave0 核实：补全 Linkage_Matrix（含 D0A/E0A 程序表在无 override 时的 class_code 派生结果、七枢纽 sheet 集合逐一比对）+ 零回归基线测试。**skip 清单与 F1-12/回函情况汇编归属已在本设计定案，M0 只做 override 派生结果核实** | 纯只读，无回退风险 |
| **M1** | 呈现治理（skip / sheet_name override / G0-3 冲突修 / G0 两张差异表可达 / 污染纠正） | 单文件 JSON，逐条可回退 |
| **M1a** | 路由解析治理（决策 8）：程序表模板 key 父码优先（L0A 生效）+ Index_Code_Map + 非兜底 componentType 契约守卫 | 纯函数 + 回退兜底，可回退 |
| **M1b** | **E0 重建（决策 4 / B 方案）**：E0-1 → `confirmation-summary`、E0-2 → `confirmation-entity-verify`、E0-7 → `confirmation-followup`、F1-12 → `confirmation-reliability`、E0A/E0-6/银行函证其他信息核对表E0-5 显式登记；E0 清单→E0-1 带入 | override 为 JSON 逐条可回退；既有数据近零（E0-1~E0-5 各 0 行）故迁移风险可忽略 |
| **M2** | Sync_To_Center 空态入口 + 只读门控 + 同步状态可见（E0 重建后自动纳入） | 单组件，可回退 |
| **M3** | Unreplied_Pull 四处落地（D0-6 / F0-5 / F0-6 / K0-5），逐套独立发布 | 每套独立可回退 |
| **M4** | Reply_Backflow 持久化读取 + 手工优先 + 台账回跳来源底稿 | 独立可回退 |
| **M5** | 属性/契约测试 + 守卫 + 七枢纽 Playwright | 仅测试 |

**M0 是硬前置**：Linkage_Matrix 未核实完不得进 M1（否则 skip 掉在用 sheet = 数据不可达）。
