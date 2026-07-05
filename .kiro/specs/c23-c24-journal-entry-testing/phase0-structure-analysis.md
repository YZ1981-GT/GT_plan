# Phase0 双源核对：C23/C24 会计分录测试结构分析

> 运行 `analyze_c_category.py` + `dump_c_content.py` + `dump_c23_c24_structure.py` + `dump_c23_c24_detail.py` 产出

## 一、Sheet 分组表

### C23 会计分录 - 控制测试（5 sheets）

| # | 源模板 sheetName | 组件内 sheetName | 维度 | 功能 |
|---|-----------------|-----------------|------|------|
| 1 | C23A 会计分录控制测试程序表 | C23A | 35×11 merged=18 | 程序表（a-program-console 风格，序号/程序/是否适用/执行人/执行情况/索引号）|
| 2 | 会计人员清单完整性测试表C23-1 | C23-1 | 40×5 merged=2 | 人员清单维护（数据来源+授权清单动态行）|
| 3 | 会计分录控制测试C23-2 | C23-2 | 72×8 merged=2 | 控制测试样本表（25笔日记账+编制/过账/审核人+偏差判断）|
| 4 | 示例 - 会计人员清单测试 | 示例1 | 41×11 merged=1 | 参考示例（只读展示）|
| 5 | 示例 - 会计分录控制测试 | 示例2 | 71×11 merged=1 | 参考示例（只读展示）|

### C24 会计分录 - 细节测试（11 sheets）

| # | 源模板 sheetName | 组件内 sheetName | 维度 | 功能 |
|---|-----------------|-----------------|------|------|
| 1 | 细节测试C24A | C24A | 53×11 merged=48 formula=8 | 程序表（含分范围/获取了解/设计策略/执行分析等步骤）|
| 2 | C24-0汇总表 | C24-0 | 129×8 merged=59 formula=6 | 审计目标+数据来源+测试工具+测试项目索引（C24-1~5+本福特）+结论 |
| 3 | C24-1完整性-借贷方发生额 | C24-1 | 41×19 merged=2 formula=6 | 借贷发生额完整性（Σ借=Σ贷）|
| 4 | C24-2完整性-分录&余额表对比 | C24-2 | 43×15 merged=5 formula=47 | 科目余额对比（分录按科目汇总 vs 试算表）|
| 5 | C24-3完整性-跳号测试 | C24-3 | 44×17 merged=2 formula=7 | 凭证号跳号识别 |
| 6 | C24-4细节测试-异常账户测试 | C24-4 | 44×14 merged=4 formula=6 | 异常账户（人员异常/异常使用账户）|
| 7 | C24-5细节测试-异常分录测试 | C24-5 | 46×16 merged=4 formula=6 | 异常分录（13+种规则筛选）|
| 8 | 参考-本福特定律测试 | 本福特 | 202×20 merged=6 formula=406 | 首位数分布统计+卡方检验（9行统计表+图表区）|
| 9 | 参考-本福特定律测试-虚拟会计分录 | 本福特-数据 | 10541×15 merged=0 formula=21079 | 虚拟分录样例数据（参考用，实际场景导入真实数据）|
| 10 | 2025假期清单 | 假期清单 | 34×5 merged=0 | 假期日历（用于异常分录"假期录入"规则）|
| 11 | GT_Custom | （内部） | 8×2 | 自定义名称区域（不渲染）|

**关键 definedNames**：`Benford数据范围`（本福特分析的数据源范围）、`本循环科目`、`bs`/`bs_1`（余额表引用）

## 二、字段映射

### C23-1 人员清单

| 区域 | 字段 | item_id 模式 | 控件 |
|------|------|-------------|------|
| 数据来源 | 文本描述 | `C23-1-source` | textarea |
| 授权人员行 | 序号 | `C23-person-{n}-seq` | auto |
| | 姓名 | `C23-person-{n}-name` | input |
| | 岗位/权限 | `C23-person-{n}-role` | el-select（创建/授权/记录）|
| | 备注 | `C23-person-{n}-note` | input |
| 测试结论 | 完整性结论 | `C23-1-conclusion` | textarea + AI |

### C23-2 控制测试样本表

| 字段 | item_id 模式 | 控件 | 说明 |
|------|-------------|------|------|
| 样本序号 | `C23-sample-{s}-seq` | auto | 1~25 |
| 凭证日期 | `C23-sample-{s}-date` | date-picker | |
| 凭证编号 | `C23-sample-{s}-voucherNo` | input | |
| 编制人 | `C23-sample-{s}-preparer` | input | |
| 过账人 | `C23-sample-{s}-poster` | input | |
| 审核人 | `C23-sample-{s}-reviewer` | input | |
| 支持性文件 | `C23-sample-{s}-supportDoc` | input + 📎 | |
| 批准过程 | `C23-sample-{s}-approval` | input | |
| 是否偏差 | `C23-sample-{s}-deviation` | el-select（是/否）| **自动核对** |
| 偏差说明 | `C23-sample-{s}-deviationNote` | textarea | |
| 索引号 | `C23-sample-{s}-indexRef` | GtIndexChip | |
| 偏差统计 | `C23-2-deviationCount` | readonly formula | |
| 测试结论 | `C23-2-conclusion` | textarea + AI | |

### C24-0 汇总表

| 区域 | 字段 | item_id 模式 | 说明 |
|------|------|-------------|------|
| 数据来源 | 应用名称 | `C24-0-source-appName` | input |
| | 应用版本 | `C24-0-source-appVersion` | input |
| | 索引号(B22A-4-3) | `C24-0-source-indexRef` | GtIndexChip |
| | 导出时间 | `C24-0-source-exportTime` | datetime |
| | 原始文件索引 | `C24-0-source-fileRef` | input |
| 测试工具 | 是否利用工具 | `C24-0-tool-used` | el-select（是/否）|
| | 工具名称 | `C24-0-tool-name` | el-select（IDEA/IAS/其他）|
| | 工具版本 | `C24-0-tool-version` | input |
| | 测试时间 | `C24-0-tool-time` | datetime |
| 测试项索引 | C24-{k} 结论 | `C24-{k}-conclusion` | 从子sheet回填 |

### C24-1 借贷方发生额

| 字段 | item_id 模式 | 引擎输出 |
|------|-------------|---------|
| 借方发生额合计 | `C24-1-debitTotal` | calcBalanceIntegrity.debitTotal |
| 贷方发生额合计 | `C24-1-creditTotal` | calcBalanceIntegrity.creditTotal |
| 是否一致 | `C24-1-balanced` | calcBalanceIntegrity.balanced |
| 测试结论 | `C24-1-conclusion` | textarea + AI |

### C24-2 科目余额对比

| 字段 | item_id 模式 | 引擎输出 |
|------|-------------|---------|
| 科目编码 | `C24-2-row-{i}-account` | compareToTrialBalance[i].account |
| 分录借方汇总 | `C24-2-row-{i}-jeDebit` | 按科目Σ借 |
| 分录贷方汇总 | `C24-2-row-{i}-jeCredit` | 按科目Σ贷 |
| 分录净额 | `C24-2-row-{i}-jeNet` | 借-贷 |
| 余额表借方 | `C24-2-row-{i}-tbDebit` | 试算表取数 |
| 余额表贷方 | `C24-2-row-{i}-tbCredit` | 试算表取数 |
| 余额表净额 | `C24-2-row-{i}-tbNet` | |
| 差异 | `C24-2-row-{i}-diff` | compareToTrialBalance[i].diff |
| 测试结论 | `C24-2-conclusion` | textarea + AI |

### C24-3 跳号测试

| 字段 | item_id 模式 | 引擎输出 |
|------|-------------|---------|
| 缺号起始 | `C24-3-gap-{i}-start` | detectGaps[i].start |
| 缺号终止 | `C24-3-gap-{i}-end` | detectGaps[i].end |
| 缺号数量 | `C24-3-gap-{i}-count` | detectGaps[i].count |
| 是否异常 | `C24-3-gap-{i}-abnormal` | el-select |
| 说明 | `C24-3-gap-{i}-note` | textarea |
| 测试结论 | `C24-3-conclusion` | textarea + AI |

### C24-4 异常账户测试

| 字段 | item_id 模式 | 说明 |
|------|-------------|------|
| 操作用户 | `C24-4-row-{i}-user` | 从分录提取 |
| 用户岗位职责 | `C24-4-row-{i}-role` | input |
| 编制单据数量 | `C24-4-row-{i}-prepareCount` | formula |
| 过账单据数量 | `C24-4-row-{i}-postCount` | formula |
| 过账单据科目分布 | `C24-4-row-{i}-accountDist` | formula |
| 审核单据数量 | `C24-4-row-{i}-reviewCount` | formula |
| 是否在会计人员清单中 | `C24-4-row-{i}-inList` | formula→boolean |
| 是否属于异常事项 | `C24-4-row-{i}-abnormal` | el-select（是/否）|
| 异常事项说明 | `C24-4-row-{i}-note` | textarea |
| 核查内容 | `C24-4-row-{i}-checkContent` | textarea |
| 结论 | `C24-4-row-{i}-conclusion` | el-select |
| 索引号 | `C24-4-row-{i}-indexRef` | GtIndexChip |

### C24-5 异常分录测试

| 字段 | item_id 模式 | 说明 |
|------|-------------|------|
| 凭证日期 | `C24-5-row-{i}-date` | formula |
| 凭证类型 | `C24-5-row-{i}-type` | formula |
| 凭证编号 | `C24-5-row-{i}-voucherNo` | formula |
| 摘要 | `C24-5-row-{i}-summary` | formula |
| 科目名称 | `C24-5-row-{i}-account` | formula |
| 对方科目 | `C24-5-row-{i}-counterAccount` | formula |
| 借方金额 | `C24-5-row-{i}-debit` | formula |
| 贷方金额 | `C24-5-row-{i}-credit` | formula |
| 辅助核算项目 | `C24-5-row-{i}-auxItem` | formula |
| 异常事项 | `C24-5-row-{i}-anomalyType` | el-tag（规则标签）|
| 异常事项说明 | `C24-5-row-{i}-anomalyNote` | textarea |
| 核查内容 | `C24-5-row-{i}-checkContent` | textarea + AI |
| 结论 | `C24-5-row-{i}-conclusion` | el-select（正常/异常-已解释/异常-错报）|
| 索引号 | `C24-5-row-{i}-indexRef` | GtIndexChip |

### 本福特定律测试

| 字段 | item_id 模式 | 引擎输出 |
|------|-------------|---------|
| 样本数量 | `C24-benford-sampleCount` | amounts.length |
| 显著性水平 | `C24-benford-alpha` | 默认0.05 |
| 首位数(1-9) | `C24-benford-digit-{d}-*` | — |
| 理论比例 | `C24-benford-digit-{d}-expected` | log10(1+1/d) |
| 实际数量 | `C24-benford-digit-{d}-count` | benfordDistribution[d].count |
| 实际比例 | `C24-benford-digit-{d}-actual` | benfordDistribution[d].actual |
| 偏差比例 | `C24-benford-digit-{d}-deviation` | actual - expected |
| 卡方贡献 | `C24-benford-digit-{d}-chi2` | (count-expected*N)²/(expected*N) |
| 卡方统计值 | `C24-benford-chi2Total` | Σchi2 |
| 检验结论 | `C24-benford-result` | 显著偏离/未显著偏离 |
| 测试结论 | `C24-benford-conclusion` | textarea + AI |

### C24 异常分录筛选规则（C24-5 参数配置）

源模板 C24-5 R25~R38 列出的 13 种异常类型：

| # | 异常规则 | 规则类型 | 引擎参数 |
|---|---------|---------|---------|
| 1 | 假期录入的分录 | 日期匹配 | `holidays: string[]`（取自2025假期清单）|
| 2 | 夜间录入的分录 | 时间段匹配 | `nightStartHour: number`（默认22）|
| 3 | 频繁调整分录 | 统计阈值 | `frequentAdjustThreshold: number` |
| 4 | 有大额分录的账户，相关金额超出正常范围 | 金额阈值 | `largeAmountThreshold: number` |
| 5 | 刚好低于审批限额 | 金额范围 | `approvalLimit: number` + 容差 |
| 6 | 分录金额为约整数 | 模式匹配 | `roundAmountDigits: number`（如末尾N个0）|
| 7 | 分录尾数一致 | 模式匹配 | `tailPattern: string` |
| 8 | 同金额或同摘要重复录入 | 重复检测 | `duplicateCheck: boolean` |
| 9 | 借贷方为不常见组合 | 科目组合 | `unusualCombinations: string[][]` |
| 10 | 账户有大量分录而又不寻常 | 统计异常 | `unusualVolumeThreshold: number` |
| 11 | 与特殊或非常规事件有关的分录 | 关键词 | `specialEventKeywords: string[]` |
| 12 | 含模糊词"调整"、"暂估"、"其他"等 | 关键词 | `vagueKeywords: string[]` |
| 13 | 没有摘要的分录 | 空值检测 | `checkEmptySummary: boolean` |

## 三、分析引擎输入/输出格式

### JournalEntry（分录导入输入）

```typescript
export interface JournalEntry {
  voucherDate: string       // 凭证日期 (YYYY-MM-DD)
  voucherMonth: number      // 凭证月份
  voucherType: string       // 凭证类型（付/收/转）
  voucherNo: string         // 凭证编号
  summary: string           // 摘要
  accountCode: string       // 科目编号
  accountName: string       // 科目名称
  debit: number             // 借方金额
  credit: number            // 贷方金额
  voucherSheets: string     // 凭证张数
  preparer: string          // 填制人
  reviewer: string          // 审核人
  poster: string            // 记账人
}
```

来源：虚拟会计分录 sheet 15 列结构（C1~C13 + C14假日标记 + C15跳号测试 = 导入时不含后两列公式列）

### useC24AnalyticsEngine 函数签名

```typescript
// 1. 借贷平衡完整性
calcBalanceIntegrity(entries: JournalEntry[]): {
  debitTotal: number
  creditTotal: number
  balanced: boolean  // abs(debitTotal - creditTotal) < 0.01
}

// 2. 科目余额对比
compareToTrialBalance(
  entries: JournalEntry[],
  trialBalance: { accountCode: string; debitAmount: number; creditAmount: number }[]
): {
  account: string; accountName: string
  jeDebitSum: number; jeCreditSum: number; jeNet: number
  tbDebit: number; tbCredit: number; tbNet: number
  diff: number
}[]

// 3. 跳号测试
detectGaps(voucherNos: string[]): {
  start: string; end: string; count: number
}[]

// 4. 异常分录筛选
interface AnomalyRules {
  holidays: string[]            // 假期日期列表
  nightStartHour: number        // 夜间起始（默认22）
  nightEndHour: number          // 夜间结束（默认6）
  largeAmountThreshold: number  // 大额阈值
  approvalLimit: number         // 审批限额
  roundAmountDigits: number     // 约整数判断位数
  vagueKeywords: string[]       // 模糊关键词
  checkEmptySummary: boolean    // 检查空摘要
  duplicateCheck: boolean       // 重复检测
}

screenAnomalies(entries: JournalEntry[], rules: AnomalyRules): {
  entry: JournalEntry
  reasons: string[]  // 命中的规则名称列表
}[]

// 5. 本福特首位数分布
benfordDistribution(amounts: number[]): {
  digit: number         // 1-9
  expected: number      // log10(1+1/digit)
  count: number         // 实际首位数为该数字的条数
  actual: number        // count / total
  deviation: number     // actual - expected
  chi2Contribution: number // (count - expected*N)² / (expected*N)
}[]

// 6. 卡方检验判断
benfordChiSquareTest(distribution: BenfordResult[], alpha?: number): {
  chi2Total: number
  criticalValue: number  // CHISQ.INV.RT(alpha, 8)
  significant: boolean   // chi2Total > criticalValue
}
```

### useC23ControlData 函数签名

```typescript
interface AuthorizedPerson {
  name: string
  role: string  // 创建/授权/记录
}

interface JeControlSample {
  seq: number
  voucherDate: string
  voucherNo: string
  preparer: string
  poster: string
  reviewer: string
  supportDoc: string
  approval: string
}

// 人员核对
checkPersonnel(
  samples: JeControlSample[],
  authorized: AuthorizedPerson[]
): {
  sample: JeControlSample
  deviation: boolean       // 任一人员不在清单
  deviationDetails: string // 具体哪个不在
}[]
```

## 四、sheetName v-if 分发映射

### GtC23JournalControl

```typescript
const SHEET_MAP_C23 = {
  'C23A': 'C23A 会计分录控制测试程序表',
  'C23-1': '会计人员清单完整性测试表C23-1',
  'C23-2': '会计分录控制测试C23-2',
  '示例1': '示例 - 会计人员清单测试',
  '示例2': '示例 - 会计分录控制测试',
} as const
```

### GtC24JournalDetail

```typescript
const SHEET_MAP_C24 = {
  'C24A': '细节测试C24A',
  'C24-0': 'C24-0汇总表',
  'C24-1': 'C24-1完整性-借贷方发生额',
  'C24-2': 'C24-2完整性-分录&余额表对比',
  'C24-3': 'C24-3完整性-跳号测试',
  'C24-4': 'C24-4细节测试-异常账户测试',
  'C24-5': 'C24-5细节测试-异常分录测试',
  '本福特': '参考-本福特定律测试',
  '本福特-数据': '参考-本福特定律测试-虚拟会计分录',
  '假期清单': '2025假期清单',
} as const
```

## 五、与 design.md 对齐确认

| 设计文档声明 | 源模板验证 | 状态 |
|---|---|---|
| C23 sheetName: C23A / C23-1 / C23-2 / 示例 | 实际5 sheets: C23A程序表 / C23-1人员清单 / C23-2控制测试 / 示例×2 | ✅ 一致（示例拆为2个）|
| C24 sheetName: C24A / C24-0 / C24-1~5 / 本福特 | 实际11 sheets: C24A / C24-0 / C24-1~5 / 本福特×2 / 假期清单 / GT_Custom | ✅ 一致（补充假期清单+GT_Custom内部）|
| JournalEntry 结构含 voucherNo/date/account/debit/credit/summary/preparer | 虚拟会计分录15列完整对应 | ✅ |
| 本福特公式 expected(d)=log10(1+1/d) | B39=LOG10(1+1/A39) | ✅ |
| 卡方检验 CHISQ.INV.RT | R49 C4公式确认 | ✅ |
| 跳号公式 | C15列 =IF(AND(B-B=0,C=C),D-D,"") 检测同类型同月凭证号间隔 | ✅ |
| 假期规则 | 内嵌2025假期清单sheet + C14列VLOOKUP+WEEKDAY公式 | ✅ |
| C24-2 47公式 | 实测 formula=47 | ✅ |
| C24本福特 406公式 + 虚拟分录21079公式 | 实测确认 | ✅ |
| C23-2 抽25笔日记账样本 | R8程序描述"25笔日记账分录样本" | ✅ |
| 人员核对：编制人/过账人/审核人 | C23-2 R9/R10 确认 | ✅ |
| C24-4 异常账户14列 | 实测14列对应 | ✅ |
| C24-5 异常分录16列 | 实测16列对应（R24表头确认）| ✅ |

## 六、注意事项

1. **C24 definedNames** 中 `Benford数据范围` 是本福特分析的核心命名区域，引擎实现时需支持类似的可配置数据范围
2. **2025假期清单** 需内置到系统（34条记录），并支持按年度更新
3. **GT_Custom** 为致同内部自定义区域，不需渲染
4. **C24-2 的47个公式** 涉及分录汇总与试算表比较，是 `compareToTrialBalance` 引擎函数的核心语义
5. **虚拟会计分录10541行** 仅为模板示例数据，实际使用时由用户导入真实分录
6. **C24-0 汇总表** 引用 C24A 的表头信息（被审计单位/编制人/日期），各测试项结论需从子sheet自动回填
