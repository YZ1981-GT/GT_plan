# D2 检查底稿双向回写覆盖 — Design

## §1 勘测结论

### 1.1 工作簿结构

D2 循环共三本 Excel 工作簿（`backend/wp_templates/D/`）：

| 工作簿 | 文件名 | 大小 | Sheet 数 | 已覆盖 |
|--------|--------|------|----------|--------|
| 审定表明细表 | `D2-1至D2-4  应收账款- 审定表明细表（Leap-常规程序）.xlsx` | 123KB | 11 | ✅ 3/3（d22/d23/d21-managed） |
| 分析程序 | `D2-5  应收账款 -分析程序（Leap应对措施-分析程序）.xlsx` | 103KB | — | 待定（本 spec 范围外） |
| **检查** | **`D2-6至D2-13  应收账款 -检查（Leap应对措施-检查）.xlsx`** | **357KB** | **12** | **🔴 0/8（本 spec 目标）** |

检查工作簿 12 张 sheet：底稿目录 / 附注(上市) / 附注(国企) / D2-6~D2-13 / GT_Custom。
其中 D2-6~D2-13 共 8 张是本 spec 的目标。

### 1.2 逐 sheet 勘测

| Sheet | Excel tab 名 | 几何 | 公式数 | 前端 Composable | store item_id | 行身份前缀 | 字段数/行 |
|-------|-------------|------|--------|----------------|--------------|-----------|----------|
| D2-6 | 关联方及交易检查表D2-6 | 31×14 | 17 | useD2RelatedParty | `D2-related-party-rows` + note + conclusion | `rp-` | 12 |
| D2-7 | 应收账款检查表D2-7 | 52×17 | 20 | useD2VoucherCheckEnhanced | `D2-vc-current-rows` / `D2-vc-post-rows` | `vcr-` | 20+ |
| D2-8 | 坏账准备计提会计政策检查D2-8 | 46×22 | 6 | useD2PolicyCheck | `D2-policy-paragraphs` / `-historical-matrix` / `-migration-matrix` + conclusion + summary | `policy-` | 混合 |
| D2-9 | 应收坏账准备测算D2-9 | 50×14 | 57 | useD2Ecl (focus=D2-9) | `D2-ecl-single-rows` / `-discount-rows` / `-migration-matrix` | `ecl-` | 8~多场景 |
| D2-10 | 预期信用损失的计量测试D2-10 | 110×10 | 198 | useD2Ecl (focus=D2-10) | 同 D2-9 | `ecl-` | 同上 |
| D2-11 | 坏账准备转回核销检查表D2-11 | 29×8 | 10 | useD2WriteoffCheck | `D2-writeoff-reversal-rows` / `-writeoff-rows` | `wo-` | 10 |
| D2-12 | 应收账款质押出售情况检查表D2-12 | 43×12 | 13 | useD2PledgeCheck | `D2-pledge-rows` / `D2-factoring-rows` + note + conclusion | `pl-` | 10/9 |
| D2-13 | 应收账款业务模式分析D2-13 | 30×5 | 12 | useD2BizModel | `D2-bizmodel-judgments` / `-groups` + note + conclusion | `bm-` | 5/6 |

### 1.3 数据库映射

- `wp_index` 里只有 `D2-5` 和 `D2-6` 有独立 wp_code；D2-7~D2-13 **没有**独立 wp_code
- `wp_code_overrides.json` 里 D2~D2-13 **全部**映射到 `d2-accounts-receivable` componentType
- 前端渲染时所有 D2 子 sheet 共用同一个 `props.wpId`（D2 主底稿的 wp_id）
- store 数据全在同一个 `working_paper` 的 `checklist_responses` 里，按 `item_id` 区分
- 真库 `checklist_responses` 里 D2-6~D2-13 的行数据**全部为零**（审计师尚未录入）

### 1.4 公式特征

检查工作簿的公式分两类：
1. **跨 sheet 引用**（`=底稿目录!A2` 等）：表头区的被审计单位名/编制人/日期，属模板元数据
2. **数据区公式**：合计行 SUM、计算列（如 D2-6 的 `endBalance = prior + debit - credit`）

公式总量 333 个（17+20+6+57+198+10+13+12），其中 D2-10 独占 198 个（最复杂）。

## §2 架构决策

### 2.1 方案 A：归入现有 entry（✅ 采纳）

**理由**：
1. D2-6~D2-13 共用同一个 `wpId`，store 在同一个 `checklist_responses` 里
2. 前端已有一个 `useWorkpaperSyncBridge` 实例（`D2_SYNC_ENTRY_ID = 'xlsx/gt-d2-accounts-receivable'`）
3. `D2_MANAGED_SHEET_KEYS` 已经是 `Record<string, string>` 结构，扩展即可
4. `build_contract_payload()` 的 `sheets[]` 数组已有模式（D2-3/D2-1 按开关追加）

**但有两个前置条件**：
- **P1**：检查工作簿是**独立的 xlsx 文件**，与审定表工作簿不同 → 需要独立的 `InstrumentationSpec`
- **P2**：一个 entry 横跨两本工作簿的 instrumentation → `instrumentation_specs()` 已返回 tuple，追加即可

### 2.2 多工作簿 instrumentation 方案

当前 `pilot_d2_large_json.py` 的 `instrumentation_specs()` 返回 1~3 个 spec（D2-2 + 开关控 D2-3/D2-1），全部指向审定表工作簿。检查工作簿需要：

1. 新增 `INSPECTION_TEMPLATE_RELATIVE_PATH`、`INSPECTION_TEMPLATE_SHA256` 常量
2. 每张检查 sheet 新增一个 `InstrumentationSpec`（template_id / managed_sheet / 几何参数）
3. `instrumentation_specs()` 追加这些 spec
4. 契约 `build_contract_payload()` 的 `sheets[]` 追加对应 sheet payload

**🔴 关键约束**：当前 `build_contract_payload()` 只引用一个模板（`TEMPLATE_SHA256`），但检查工作簿是另一个模板。契约层需要支持多模板——**或者**，为检查工作簿创建独立的 entry。

### 2.3 最终方案：检查工作簿独立 entry（✅ 修正决策）

经深入分析，**检查工作簿应该有自己的 entry**：

1. **模板不同**：审定表工作簿和检查工作簿是两个独立的 xlsx 文件，各自有不同的 `template_sha256`
2. **instrumentation 不共享**：注入 row UUID、defined names 等操作是 per-workbook 的
3. **契约的 `template` 节只能指向一个模板**：当前 schema 不支持多模板
4. **发布链独立**：`template → instrumentation → contract → bundle → representation` 是 per-entry 的

**新 entry 设计**：
- `entry_id`: `xlsx/gt-d2-inspection`
- `adapter_id` / `contract_id`: `d2.inspection`
- `wp_codes`: `{"D2-6"}` 或按 override 指派
- 模板：`D/D2-6至D2-13  应收账款 -检查（Leap应对措施-检查）.xlsx`
- 前端：`GtD2AccountsReceivable.vue` 同时持有两个 bridge（主 entry + 检查 entry），按 sheet 切换

### 2.4 实施优先级

鉴于工作量（~40h）和真库零数据的现状，分两期：

**Phase 1（本 spec）：前端接桥 + sheet map 扩展**
- 只做前端侧扩展：`D2_MANAGED_SHEET_KEYS` 加入 D2-6~D2-13
- 前端 watch 补齐（受管 sheet 间切 tab 重开 OO）
- 不写后端 provider（真库零数据，无法实测 roundtrip）

**Phase 2（后续 spec）：后端 provider + 契约 + instrumentation**
- 新建 `pilot_d2_inspection.py` 模块
- 逐 sheet 写 provider（D2-6~D2-13）
- 契约生成 + instrumentation 注入
- 真库有数据后 roundtrip 验证

**🔴 修正**：Phase 1 的前提是——检查工作簿的 OO 编辑**不依赖** provider/契约/instrumentation。当前架构下，`switchToOnlyOffice()` 需要 `entry_state` 里有 published representation。如果检查工作簿没有走过发布链，OO 切换会报 `StorePhaseRejectedError`。

**因此 Phase 1 实际可做的范围**：
1. 确认检查工作簿能否走 `single_onlyoffice` 模式（legacy GtOnlyOfficeSheet，不经 bridge）
2. 如果不能走 bridge，只扩展 `KNOWN_HTML_SHEETS` + 工具栏显示

## §3 逐 sheet 数据结构精读

### D2-6 关联方及交易检查表（最简单，首个实施）

```
RelatedPartyRow {
  rowId: string        // rp-{ts36}-{rand}
  debtorName: string   // 关联方名称 → Excel B列
  relationType: string // 关联关系类型 → C列
  transactionType: string // 交易类型 → D列
  priorBalance: number // 期初余额 → E列
  debitAmount: number  // 本期借方 → F列
  creditAmount: number // 本期贷方 → G列
  endBalance: number   // 期末余额 = E+F-G → H列（公式）
  badDebtProvision: number // 坏账准备 → I列
  bookValue: number    // 账面价值 = H-I → J列（公式）
  isArmsLength: string // 是否公允 → K列
  remark: string       // 备注 → L列
}
```
store: 3 个 item_id（rows / note / conclusion）

### D2-11 核销检查表

```
WriteoffRow {
  rowId: string        // wo-{ts36}-{rand}
  section: 'reversal' | 'writeoff'
  debtorName: string   // 债务人 → B列
  amount: number       // 金额 → C列
  originalDate: string // 原确认日期 → D列
  reason: string       // 原因 → E列
  approvalDoc: string  // 审批文件 → F列
  isReasonable: string // 是否合理 → G列
  auditorComment: string // 审计师意见 → H列（无 indexRef 在 excel 里）
  indexRef: string     // 索引号
}
```
store: 2 个 item_id（reversal-rows / writeoff-rows）→ 对应 Excel 里两个区域

### D2-12 质押出售检查表

双表：PledgeRow（10 字段）+ FactoringRow（9 字段），各自独立 store key。

### D2-13 业务模式分析

双结构：BizModelJudgment（固定问题列表，questionId 作身份）+ BizModelGroup（动态行，rowId=bm-*）

### D2-7 应收账款检查表

最宽（20+ 字段），双区（current / post），含 OCR/附件元数据。

### D2-8 坏账政策检查

混合型：段落（paragraphId，固定 6 条）+ 历史损失率矩阵 + 迁徙率矩阵。

### D2-9/D2-10 ECL 测试

最复杂。D2-9 = 单项 ECL 行（8 字段）。D2-10 = 迁徙率矩阵 + 折现法（含概率场景数组）。198 个公式。
