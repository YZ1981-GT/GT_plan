# Phase0 双源核对分析报告

> C23 会计分录控制测试 + C24 会计分录细节测试

## 一、源模板概览

| 底稿 | 文件名 | Sheets | 总公式数 |
|------|--------|--------|----------|
| C23 | C23 会计分录 - 控制测试.xlsx | 5 | 0 |
| C24 | C24 会计分录 - 细节测试.xlsx | 11 | 21,552 (主要在虚拟分录+本福特) |

---

## 二、C23 Sheet 结构

### sheetName 分发表

| sheetName (源模板) | 组件内标识 | 功能 | 维度 | 公式 |
|---|---|---|---|---|
| C23A 会计分录控制测试程序表 | `C23A` | 程序表（a-program-console 语义） | 35×11 | 0 |
| 会计人员清单完整性测试表C23-1 | `C23-1` | 人员清单完整性测试 | 40×5 | 0 |
| 会计分录控制测试C23-2 | `C23-2` | 控制测试（25笔样本） | 72×8 | 0 |
| 示例 - 会计人员清单测试 | `C23-示例1` | 示例（只读参考） | 41×11 | 0 |
| 示例 - 会计分录控制测试 | `C23-示例2` | 示例（只读参考） | 71×11 | 0 |

### C23-1 人员清单结构

- 区域：测试程序说明 + 数据来源 + 测试记录表 + 测试结果 + 测试结论
- 测试记录表列：未在源模板明确定义列头（需从示例推断）
- 示例列结构（从"示例 - 会计人员清单测试" R25）：

| 列 | 字段 |
|----|------|
| A | 用户编号 |
| B | 全名 |
| C | 职位 |
| D | 职责 |
| E | 编制分录 (√/N/A) |
| F | 批准分录 (√/N/A) |
| G | 过账 (√/N/A) |

### C23-2 控制测试样本结构

- 程序：25笔日记账样本 → 核对编制人/过账人/审核人
- 10步流程：总体定义→来源→数量→控制性质频率→风险→偏差定义→样本数量→测试记录→扩大范围→结论
- 样本记录列（从示例 R55）：

| 列 | 字段 |
|----|------|
| A | 样本编号 |
| B | 凭证号 |
| C | 记账日期 |
| D | 摘要 |
| E | 支持文件类型及识别特征 |
| F | 编制人 |
| G | 记账人 |
| H | 注释 |

- 偏差定义：①编制/复核/批准人不符授予职责 ②支持性/批准性文件不符记账政策

---

## 三、C24 Sheet 结构

### sheetName 分发表

| sheetName (源模板) | 组件内标识 | 功能 | 维度 | 公式 |
|---|---|---|---|---|
| 细节测试C24A | `C24A` | 程序表 | 53×11 | 8 |
| C24-0汇总表 | `C24-0` | 汇总表（数据来源+测试项索引+结论） | 129×8 | 6 |
| C24-1完整性-借贷方发生额 | `C24-1` | 借贷发生额一致性 | 41×19 | 6 |
| C24-2完整性-分录&余额表对比 | `C24-2` | 科目余额表对比 | 43×15 | 47 |
| C24-3完整性-跳号测试 | `C24-3` | 凭证号跳号检测 | 44×17 | 7 |
| C24-4细节测试-异常账户测试 | `C24-4` | 异常账户/人员测试 | 44×14 | 6 |
| C24-5细节测试-异常分录测试 | `C24-5` | 异常分录筛选（规则驱动） | 46×16 | 6 |
| 参考-本福特定律测试 | `benford` | 本福特首位/前两位数分布 | 202×20 | 406 |
| 参考-本福特定律测试-虚拟会计分录 | `benford-data` | 虚拟分录数据(10540行) | 10541×15 | 21,079 |
| 2025假期清单 | `holidays` | 法定假期+调休 | 34×5 | 0 |
| GT_Custom | `gt-custom` | 自定义配置（8行） | 8×2 | 0 |

---

## 四、C24 各 Sheet 列结构详解

### C24-0 汇总表

**测试基本信息区 (R8-R21)：**
- 数据来源：应用程序名称/版本/索引号(B22A-4-3)/导出时间/原始文件索引
- 测试工具：是否利用工具/名称(IDEA/IAS)/版本/测试时间/详细索引

**测试项索引区 (R24-R45)：**

| 序号 | 项目 | 索引号 |
|------|------|--------|
| 1 | 会计分录完整性测试 | — |
| 1.1 | 借贷发生额一致性 | C24-1 |
| 1.2 | 科目余额表对比 | C24-2 |
| 1.3 | 跳号测试 | C24-3 |
| 2 | 日常异常会计分录测试 | — |
| 2.1 | 分录由未授权职员录入 | C24-4 |
| 2.2 | 无编制人/不恰当名字凭证 | C24-4 |
| 2.3 | 高管/IT人员制作分录 | C24-4 |
| 2.4 | 账户大量分录不寻常活动 | C24-5 |
| 2.5 | 大额分录超正常范围 | C24-5 |
| 2.6 | 特殊/非常规事件分录 | C24-5 |
| 2.7 | 没有摘要的分录 | C24-5 |
| 2.8 | 约整数的分录 | C24-5 |
| 参考 | 本福特定律测试 | 参考-本福特 |
| 3 | 高层调整/结账/抵消分录 | — |
| 3.1~3.5 | 重大会计分录/无关联/权益/舞弊/非惯常 | C24-4 |

### C24-1 借贷发生额

列：借方发生额汇总 | 贷方发生额汇总 | 差异 | 产生差异原因 | 结论 | 索引号 | 备注

### C24-2 分录余额表对比

双区对比结构（15列）：

| 区域 | 列 | 字段 |
|------|-----|------|
| 分录汇总 | A | 科目编码 |
| | B | 科目名称 |
| | C | 发生额 |
| | D | 被审计单位最后调整 |
| | E | 调整后发生额 (=C+D) |
| 科目余额表 | F(实际H) | 科目编码 |
| | G(实际I) | 科目名称 |
| | H(实际J) | 期初余额 |
| | I(实际K) | 被审计单位最后调整 |
| | J(实际L) | 期末余额 |
| | K(实际M) | 本期发生额 (=L-J 即期末-期初) |
| 结论 | L(实际N) | 被审计单位最后调整前 差异(=E-M) |
| | M(实际O) | 被审计单位最后调整后 差异 |

公式语义：`E=C+D`, `M=L-J(期末-期初)`, `差异前=E-M`, `差异后=F-N`

### C24-3 跳号测试

列：序号 | 年度 | 月份 | 缺号区间 | 是否属于异常跳号 | 说明 | 结论 | 索引号 | 备注

关键公式 B37（结论）：
```
=IF(
  COUNTIF('虚拟会计分录'!O2:O10541,">1") > 0,
  "存在跳号异常（"& COUNTIF(...) &"个异常事项）",
  "无跳号异常"
)
```
O列公式（跳号检测）：`=IF(AND(B_n - B_(n-1) = 0, C_n = C_(n-1)), D_n - D_(n-1), "")`
- 语义：同月份+同类型时，凭证编号差值 >1 即为跳号

### C24-4 异常账户测试

列（14列）：序号 | 操作用户 | 用户岗位职责 | 编制单据数量 | 过账单据数量 | 过账单据科目分布 | 审核单据数量 | 是否在会计人员清单中 | 是否属于异常事项 | 异常事项说明 | 核查内容 | 结论 | 索引号 | 备注

### C24-5 异常分录测试

列（16列）：序号 | 凭证日期 | 类型 | 编号 | 摘要 | 科目名称 | 对方科目 | 借方金额 | 贷方金额 | 辅助核算项目 | 异常事项 | 异常事项说明 | 核查内容 | 结论 | 索引号 | 备注

---

## 五、异常分录规则清单（C24-5）

源模板定义的 13 条异常规则（分组行标题）：

| # | 规则名称 | 规则类型 | 参数 |
|---|----------|----------|------|
| 1 | 假期录入的分录 | 日期匹配 | holidays清单 + 周末 |
| 2 | 夜间录入的分录 | 时间窗口 | nightStartHour (默认22:00) |
| 3 | 频繁调整分录 | 频次统计 | 同科目/同摘要重复次数阈值 |
| 4 | 大额分录超正常范围 | 金额阈值 | largeAmountThreshold |
| 5 | 刚好低于审批限额 | 金额区间 | approvalLimit, 容差比例 |
| 6 | 分录金额为约整数 | 金额模式 | 整千/整万/整十万判断 |
| 7 | 分录尾数一致 | 金额模式 | 尾数重复检测 |
| 8 | 同金额或同摘要重复录入 | 重复检测 | 完全匹配/近似匹配 |
| 9 | 借贷方为不常见组合 | 科目匹配 | 常见科目组合白名单 |
| 10 | 账户大量分录不寻常活动 | 频次统计 | 科目分录数量阈值 |
| 11 | 与特殊/非常规事件有关 | 摘要关键词 | 用户自定义关键词 |
| 12 | 含模糊词"调整/暂估/其他"等 | 摘要关键词 | 默认词库 |
| 13 | 没有摘要的分录 | 空值检测 | — |

---

## 六、本福特定律测试结构

### 测试参数
- 数据范围：`Benford数据范围` = 虚拟分录!$H$2:$I$10541（借方+贷方金额）
- 显著性水平：0.05
- 检验方法：卡方检验 (Chi-Square Test)

### 首位数分布（行38-47，digit 1-9）

| 列 | 字段 | 公式 |
|----|------|------|
| A | 首位数 (1-9) | 固定值 |
| B | 理论比例 | `=LOG10(1+1/A)` |
| C | 实际数量 | `{=SUMPRODUCT(--(LEFT(TEXT(ABS(range),"0E+0"),1)=TEXT(A,"0")),--ISNUMBER(range),--(range<>0))}` |
| D | 实际比例 | `=C/D$16` (D16=样本总数) |
| E | 偏差比例 | `=IF((D-B)=0,"",(D-B))` |
| F | 卡方贡献 | `=(C-B*D$16)^2/(B*D$16)` |
| G | 说明 | 手工 |
| H | 结论 | 手工 |

### 前两位数分布（行67-157，digit 10-99）

同结构，D列分母改为 `SUM($C$68:$C$157)`

### 结论公式
- 首位数卡方统计值 (R49)：`=SUM(F39:F47)`
- 判断 (R49-D)：`=IF(C49 > CHISQ.INV.RT(0.05, 8), "显著偏离", "未显著偏离")`
- 前两位卡方统计值 (R159)：`=SUM(F68:F157)`
- 判断 (R159-C)：`=IF(C159 > CHISQ.INV.RT(0.05, 89), "显著偏离", "未显著偏离")`

### 样本总数公式 (D16)
`{=SUMPRODUCT(--ISNUMBER(Benford数据范围),--(Benford数据范围<>0))}`

---

## 七、虚拟分录数据结构（引擎输入规格）

### 分录导入字段（15列 → JournalEntry 接口）

| 列 | 源字段 | 引擎字段 | 类型 | 必填 |
|----|--------|----------|------|------|
| A | 凭证日期 | `date` | string (YYYY-MM-DD) | ✓ |
| B | 凭证月份 | `month` | number | ✓ |
| C | 凭证类型 | `voucherType` | string (付/收/转) | ✓ |
| D | 凭证编号 | `voucherNo` | number | ✓ |
| E | 摘要 | `summary` | string | |
| F | 科目编号 | `accountCode` | string | ✓ |
| G | 科目名称 | `accountName` | string | |
| H | 借方金额 | `debit` | number | ✓ |
| I | 贷方金额 | `credit` | number | ✓ |
| J | 凭证张数 | `attachmentCount` | number | |
| K | 填制人 | `preparer` | string | |
| L | 审核人 | `reviewer` | string | |
| M | 记账人 | `poster` | string | |

### 计算列（N/O）

| 列 | 功能 | 公式语义 |
|----|------|----------|
| N | 法定假日标记 | 周末(WEEKDAY>5)或公共假日→"休息日-{节日名}"; 调休日→"工作日-{补班}"; 否则→"工作日" |
| O | 跳号检测 | 同月同类型时，相邻凭证编号差值；差值>1表示跳号 |

---

## 八、引擎输入/输出规格

### useC24AnalyticsEngine 接口

```typescript
// === 输入 ===
interface JournalEntry {
  date: string          // YYYY-MM-DD
  month: number         // 1-12
  voucherType: string   // 付/收/转
  voucherNo: number     // 凭证编号
  summary?: string
  accountCode: string
  accountName?: string
  debit: number
  credit: number
  attachmentCount?: number
  preparer?: string     // 填制人
  reviewer?: string     // 审核人
  poster?: string       // 记账人
}

interface TrialBalanceRow {
  accountCode: string
  accountName: string
  openingBalance: number
  closingBalance: number
  adjustedAmount?: number  // 被审计单位最后调整
}

interface AnomalyRules {
  holidays: string[]              // YYYY-MM-DD 假期清单
  nightStartHour: number          // 夜间起始(默认22)
  nightEndHour: number            // 夜间结束(默认6)
  largeAmountThreshold: number    // 大额阈值
  approvalLimit: number           // 审批限额
  approvalTolerance: number       // 临界容差比例(如0.9=限额90%~100%)
  roundAmountLevels: number[]     // 约整数级别[1000,10000,100000]
  frequencyThreshold: number      // 频繁调整次数阈值
  suspiciousKeywords: string[]    // 可疑关键词["调整","暂估","其他"]
}

// === 输出 ===

// C24-1: 借贷平衡
interface BalanceIntegrity {
  debitTotal: number
  creditTotal: number
  difference: number
  balanced: boolean  // |difference| < epsilon
}

// C24-2: 科目余额对比
interface AccountComparison {
  accountCode: string
  accountName: string
  jeAmount: number          // 分录发生额汇总
  jeAdjusted: number        // 调整后发生额
  tbOpeningBalance: number
  tbClosingBalance: number
  tbPeriodAmount: number    // 本期发生额=期末-期初
  diffBeforeAdj: number     // jeAmount - tbPeriodAmount
  diffAfterAdj: number      // jeAdjusted - tbAdjustedAmount
}

// C24-3: 跳号
interface GapItem {
  year: number
  month: number
  voucherType: string
  gapStart: number
  gapEnd: number
  count: number             // 缺号个数
  isAbnormal?: boolean
  note?: string
}

// C24-4: 异常账户
interface AbnormalAccount {
  operator: string
  role: string
  prepareCount: number
  postCount: number
  postAccountDistribution: string
  reviewCount: number
  inAuthorizedList: boolean
  isAbnormal: boolean
  note?: string
  conclusion?: string
}

// C24-5: 异常分录
interface AnomalyEntry {
  entry: JournalEntry
  counterAccount?: string
  reasons: string[]         // 命中的异常规则名
  explanation?: string
  verificationContent?: string
  conclusion?: string
}

// 本福特
interface BenfordResult {
  digit: number             // 1-9 (首位) 或 10-99 (前两位)
  expected: number          // log10(1 + 1/d)
  actualCount: number
  actualRatio: number
  deviation: number         // actualRatio - expected
  chiContribution: number   // (count - expected*N)^2 / (expected*N)
}

interface BenfordSummary {
  sampleSize: number
  significanceLevel: number  // 0.05
  firstDigit: BenfordResult[]       // 9 items
  firstTwoDigits: BenfordResult[]   // 90 items (10-99)
  chiSquareFirst: number
  chiSquareTwo: number
  conclusionFirst: '显著偏离' | '未显著偏离'
  conclusionTwo: '显著偏离' | '未显著偏离'
}
```

### useC23ControlData 接口

```typescript
interface AuthorizedPerson {
  userId: string
  name: string
  role: string
  canPrepare: boolean
  canApprove: boolean
  canPost: boolean
}

interface JeControlSample {
  sampleNo: number
  voucherNo: string
  date: string
  summary: string
  supportDoc: string
  preparer: string
  poster: string
  reviewer?: string
  note?: string
}

interface PersonnelCheckResult {
  sample: JeControlSample
  preparerAuthorized: boolean
  posterAuthorized: boolean
  reviewerAuthorized: boolean
  deviation: boolean         // any false above
  deviationType?: string     // "编制人未授权" | "记账人未授权" | ...
}
```

---

## 九、item_id 命名规范

### C23 前缀

| 区域 | item_id 模式 | 示例 |
|------|-------------|------|
| C23A 程序表 | `C23A-step-{n}-{field}` | C23A-step-1-applicable |
| C23-1 人员清单 | `C23-1-person-{n}-{field}` | C23-1-person-1-name |
| C23-1 测试结论 | `C23-1-conclusion` | — |
| C23-2 样本 | `C23-2-sample-{n}-{field}` | C23-2-sample-1-preparer |
| C23-2 样本偏差 | `C23-2-sample-{n}-deviation` | C23-2-sample-1-deviation |
| C23-2 测试结论 | `C23-2-conclusion` | — |

### C24 前缀

| 区域 | item_id 模式 | 示例 |
|------|-------------|------|
| C24-0 数据来源 | `C24-0-source-{field}` | C24-0-source-appName |
| C24-0 测试项结论 | `C24-0-item-{k}-conclusion` | C24-0-item-1.1-conclusion |
| C24-1 借贷结果 | `C24-1-{field}` | C24-1-debitTotal |
| C24-1 结论 | `C24-1-conclusion` | — |
| C24-2 科目行 | `C24-2-row-{n}-{field}` | C24-2-row-1-accountCode |
| C24-2 结论 | `C24-2-conclusion` | — |
| C24-3 跳号行 | `C24-3-gap-{n}-{field}` | C24-3-gap-1-range |
| C24-3 结论 | `C24-3-conclusion` | — |
| C24-4 异常账户 | `C24-4-account-{n}-{field}` | C24-4-account-1-operator |
| C24-4 结论 | `C24-4-conclusion` | — |
| C24-5 异常分录 | `C24-5-anomaly-{n}-{field}` | C24-5-anomaly-1-reason |
| C24-5 规则参数 | `C24-5-rules-{ruleKey}` | C24-5-rules-largeAmount |
| C24-5 结论 | `C24-5-conclusion` | — |
| 本福特参数 | `C24-benford-{field}` | C24-benford-significance |
| 本福特结论 | `C24-benford-conclusion-first` | — |
| 审计说明/结论 | `C24-{k}-note` / `C24-{k}-opinion` | — |

---

## 十、公式语义总结

### C24A 程序表公式
- B26~B33：引用 C24-0 汇总表 R30~R37 结论（`='C24-0汇总表'!B30`）

### C24-0 汇总表公式
- A3/C3/E3/A4/C4/E4：引用 C24A 表头（被审计单位/编制人/日期）

### C24-2 科目对比公式
- E列：`=C+D`（发生额+调整=调整后发生额）
- L列(实际N)：`=K-I`（期末-期初=本期发生额）
- 差异前(N)：`=E-L`
- 差异后(O)：`=F-M`（含调整版对比）
- 合计行：`=SUM(col27:col34)`

### C24-3 跳号公式
- O列：`=IF(AND(B_n-B_(n-1)=0, C_n=C_(n-1)), D_n-D_(n-1), "")`
  - 同月+同类型→计算凭证号差值，>1 即跳号
- 结论 B37：统计 O列中 >1 的个数

### 本福特公式
- 理论比例：`=LOG10(1+1/d)`
- 实际数量：`{=SUMPRODUCT(--(LEFT(TEXT(ABS(range),"0E+0"),1)=TEXT(d,"0")),...)}` 数组公式
- 实际比例：`=C/N`（N=样本总数）
- 偏差：`=IF((D-B)=0,"",(D-B))`
- 卡方贡献：`=(C-B*N)^2/(B*N)`
- 卡方总值：`=SUM(F39:F47)`
- 结论：`=IF(chiSq > CHISQ.INV.RT(α, df), "显著偏离", "未显著偏离")`

### 虚拟分录 N列（假期/周末标记）
```
=IF(
  OR(WEEKDAY(date,2)>5, VLOOKUP(date,holidays,5)="public_holiday"),
  IF(VLOOKUP(date,holidays,5)="transfer_workday",
     "工作日-"&holiday_name, 
     "休息日-"&IF(holiday_name<>"", holiday_name, "周末")),
  "工作日"
)
```

---
