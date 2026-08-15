# Implementation Plan: 可编辑金额控件迁移与列类型判据

## Overview

10 个任务分 5 波。**判据先行**是本 spec 的第一原则：Wave 1 建列类型真源与探针，
Wave 2 建正反双向断言并做变异检验，之后才开始迁移。

理由是本次实测暴露的两件事：旧探针以「有没有写 `:formatter`」为必要条件（漏掉
I1-10/I1-11 这类无 formatter 的金额列），现有反向边界断言在未迁移代码上恒真
（没有区分能力，迁移过程本身会引入「年限显示 `1,000.00`」的新缺陷）。

存量实测：`el-input-number` **4260 处 / 798 文件**，其中带 `:formatter` 的空操作
**80 处 / 13 文件**；`WpAmountInput` 已覆盖 682 处 / 118 文件；疑似金额列违规
**1064 处**（粗判候选，须逐项复核）。

## Tasks

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "name": "列类型真源与探针（判据先行）",
      "tasks": ["1", "2"],
      "parallel": false,
      "rationale": "Task 2 的探针 import Task 1 的真源纯函数，强依赖"
    },
    {
      "wave": 2,
      "name": "正反双向断言与能力证明",
      "tasks": ["3", "4"],
      "parallel": false,
      "rationale": "Task 4 的变异检验需要 Task 3 的断言存在才能验证其区分能力"
    },
    {
      "wave": 3,
      "name": "批 1 — 80 处 formatter 空操作",
      "tasks": ["5", "6"],
      "parallel": false,
      "rationale": "Task 6 的浏览器实测依赖 Task 5 的迁移已落地"
    },
    {
      "wave": 4,
      "name": "批 2 — I 循环摊销测算表（本次实证漏网点）",
      "tasks": ["7", "8"],
      "parallel": false,
      "rationale": "同上：先迁移后实测"
    },
    {
      "wave": 5,
      "name": "批 3+ 规划与收口",
      "tasks": ["9", "10"],
      "parallel": false,
      "rationale": "Task 10 的 CI 挂载需要 Task 9 确定的剩余批次范围"
    }
  ]
}
```

---

- [x] 1. 列类型判定单一真源

  - 新建 `audit-platform/frontend/src/components/workpaper/shared/amountColumnSemantics.ts`
  - `AMOUNT_LABEL_PATTERNS`（金额/余额/原值/成本/价值/净额/摊销/折旧/减值/残值/收入/费用/支出…）
  - `NON_AMOUNT_LABEL_PATTERNS` 覆盖 R1.2 的 19 类：比率/利率/汇率/占比/比例/年限/期限/
    月份/月数/天数/笔数/数量/股数/份数/年度/折现率/增长率/毛利率/税率
  - `EXPLICIT_OVERRIDES`：按 `文件:列label` 显式裁决，每条**必带 `evidence`**
    （源模板依据或实测证据，禁止凭常识添加）
  - `classifyColumnLabel(label)` → `'amount' | 'non_amount' | 'ambiguous'`；
    🔴 两类模式都命中时返回 `'ambiguous'`，**不静默二选一**（实测存在 5 处此类 label）
  - 该模块**不被前端运行时消费**，只服务判据与迁移脚本；放 `src` 下便于 vitest 直接 import，
    避免前后端两份关键词副本
  - 🔴 模块 doc 里**显式声明边界**：本模块只服务**可编辑控件**的选型判定；
    只读展示金额归 `displayPrefs.fmtAmount()` 口径（setup 顶层
    `inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()`），
    I 循环 Task 18 已收口 16 个 SFC 的 7 种本地 `fmtAmount`，本 spec 不重复处理
  - 守卫 `shared/__tests__/amountColumnSemantics.spec.ts`：19 类关键词逐一断言 +
    歧义判定 + override 的 evidence 非空 + 边界声明存在性
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [x] 2. 全库探针（能力必须强于旧探针）

  - 新建 `backend/scripts/check/audit_amount_input_columns.py`，支持 `--check` / `--json`
  - 🔴 **判据是「金额语义列 ∧ 控件 ≠ WpAmountInput」，不得以 `:formatter` 存在为必要条件**
    —— 这正是 Task 18 探针漏掉 I1-10/I1-11 的原因；`has_formatter` 只作输出字段
  - 🔴 **按 `<el-table-column>` … `</el-table-column>` 块配对扫描**（自闭合单独处理），
    **禁止固定字符窗口** —— Task 18 首版用 400 字符窗口报 22 处，逐标签复核发现
    全是 `style="width:100%"` 的 `%` 落进窗口造成的误报
  - 多级表头的 label 需拼接父组名；`:label` 动态绑定/表达式记入 `ambiguous`
    并标 `reason: 'dynamic_label'`，**不静默丢弃**（占比 >10% 视为探针能力不足）
  - 输出 `backend/data/amount_input_migration_status.json`（schema 见 design）：
    `confirmed_violation` / `reverse_violation` / `ambiguous` / `ok_count`，
    三类之和须等于扫到的「表列 × 可编辑控件」总数（无遗漏桶）
  - **反向自检三条**：已迁移金额列不报违规 / `el-input-number` 年限列不报违规 /
    `el-input-number` 金额列必报违规
  - 禁 fail-open：解析失败记 ERROR 并影响退出码，不得吞异常当 `ok`
  - _Requirements: 2.1, 2.4, 2.5, 2.6_

- [x] 3. 正反双向断言（解决「反向边界恒真」）

  - 新建 `.../__tests__/amountInputColumnTyping.spec.ts`
  - **正向**：`confirmed_violation` 按批次筛选后为空（已完成批次）
  - **反向**：`WpAmountInput` 不得出现在 `non_amount` 列；失败消息给出
    文件名 + 列 label + 命中的非金额语义类别
  - 🔴 **扫描面非空自检**：反向断言必须至少有一个**已迁移文件**参与，
    否则该断言在未迁移代码上恒真（这正是 Task 18 的 Property 30 的缺陷）
  - **能力定向验收（本 spec 相对 Task 18 的增量证明）**：
    - 探针在 `i1/amortization/I1TabAmortizationNoImpair.vue` 与
      `I1TabAmortizationWithImpair.vue` 上**必须报出**金额列违规，
      违规 label 含「原值」与「残值」（旧探针在此报 0 处）
    - 同两文件的「使用期限(年)」列**必须不报**违规（它本就该是 `el-input-number`）
  - 天然反向样本：`j1/analysis/J1TabIndustryCompare.vue`(20 处) 与
    `d4/analysis/D4TabProductMargin.vue`(18 处) 大概率多为比率列，
    用作「不得被误迁移」的锚点
  - _Requirements: 2.2, 2.3, 3.1, 3.2, 3.3_

- [x] 4. 变异检验（证明断言有区分能力）

  - 新建 `backend/scripts/check/mutate_amount_column_typing.py`（`--list` / `--only X` / `--restore`）
  - 锚点至少覆盖：
    - 把某已迁移文件的年限列改成 `WpAmountInput` → 反向断言必红
    - 把某已迁移的金额列改回 `el-input-number` → 正向断言必红
    - 给 `classifyColumnLabel` 的非金额模式删一个关键词 → 真源守卫必红
    - 把探针的块配对扫描改成字符窗口 → 误报数上升，`ambiguous` 占比自检必红
  - 四态判定（RED / GREEN / ANCHOR-MISS / WRONG-TEST），只有 RED 且命中预期测试名算通过
  - _Requirements: 3.1_

- [x] 5. 批 1 迁移 — 80 处 `:formatter` 空操作（13 文件）

  - 新建 `backend/scripts/fix/fix_amount_input_batch.py`（幂等 + `--check` + 反向自检 + `--batch N`）
  - 目标文件与处数（实测）：`k1/core/K1TabDisclosureSoe.vue`(21) ·
    `k1/core/K1TabDisclosureListed.vue`(15) · `e1/E1TabBankDetail.vue`(11) ·
    `e1/E1TabAnalysis.vue`(9) · `e1/E1TabCashDetail.vue`(5) ·
    `e1/E1TabDigitalCurrency.vue`(5) · `e1/E1TabInterestAnalysis.vue`(4) ·
    `e1/E1TabReconciliation.vue`(3) · `e1/E1TabAdjustment.vue`(2) ·
    `k1/core/K1StageEclTable.vue`(2) · `e1/E1TabAccruedInterest.vue`(1) ·
    `e1/E1TabCertificateCount.vue`(1) · 其余 1 处
  - 🔴 **逐列先过 `classifyColumnLabel`**：写了 `:formatter` 不等于是金额列
    （作者可能误加），判为 `non_amount` 的只删 `:formatter` 不换控件
  - 等价性逐项保留：`v-model` 路径 / `@change` 名 / `:min` `:max` `:disabled` 表达式逐字相同；
    **原无 `:min` 不得新增**（备抵/调整列需负数）；`:controls="false"` 迁移后不得残留 `:controls`
  - 🔴 **不改任何 `:precision`**（业务粒度需确认，本 spec 只登记）
  - 目标文件若 `git status` 为 `M`（并发会话在改）→ **跳过并登记**，不覆盖
  - _Requirements: 4.1, 4.2, 4.5, 5.1, 5.2, 5.3, 4.4_

- [ ] 6. 批 1 浏览器实测 + 数据复原

  - 实测判据：金额列输 `1234567.5` → 失焦显示 **`1,234,567.50`**；
    聚焦时回到原始值可编辑；粘贴 `1,234,567.50` 可解析；非法输入不写 `NaN`
  - 🔴 **同行格式一致性**：同一行内可编辑金额列与只读派生列的格式必须一致
    —— 本次 I1-10 实测暴露的正是 `50000.00`（可编辑）与 `9,871.40`（只读）并存
  - 持久化类型验证：`checklist_responses` 里该字段仍为 number，不得为带逗号字符串
  - 写库前抓基线、测完先关页面（导航 `about:blank`）再 `--restore`，
    并以 `--diff` 输出「无漂移」为证
  - 辐射面串行跑（`--no-file-parallelism`），禁跑前端全量
  - _Requirements: 4.3, 5.4, 5.5, 6.1, 6.2_

- [x] 7. 批 2 迁移 — I 循环摊销测算表（本次浏览器实证的漏网点）

  - 目标：`i1/amortization/I1TabAmortizationNoImpair.vue`（I1-10）与
    `I1TabAmortizationWithImpair.vue`（I1-11）
  - 金额列（迁移）：原值 / 累计摊销期初 / 账面累计摊销期末 / 账面本期摊销 / 残值 /
    减值准备 / 账面月摊销额
  - 🔴 **非金额列（不迁移，且必须被反向断言保护）**：使用期限(年)
  - 🔴 **`使用期限(年)` 的 `:precision="2"` 不改**：现显示 `10.00`，年限是否允许小数
    需业务确认 —— 改 `:precision="0"` 会禁掉 `2.5 年` 这类录入。本 Task 只在
    tasks.md 登记该待确认项，不擅改
  - 迁移后 Task 3 的能力定向验收断言应从「报违规」转为「零违规」，
    同时反向断言的扫描面因此变非空
  - _Requirements: 4.1, 4.2, 4.4, 5.1, 5.2, 5.3_

- [ ] 8. 批 2 浏览器实测（I1-10 定点复验）

  - 复现本次实测路径：I1 主入口 → 「摊销测算表（不含减值）I1-10（剩余年限法）」→
    `+ 新增行` → 填 原值 `1234567.5` / 残值 `50000` / 使用期限 `10`
  - 判据：
    - 原值显示 `1,234,567.50`、残值显示 `50,000.00`（迁移前为 `1234567.50` / `50000.00`）
    - **使用期限仍显示 `10.00` 不带千分符**（反向边界，输 `1000` 须显示 `1000.00` 而非 `1,000.00`）
    - 只读派生列 期初净值F `1,184,567.50` / 月摊销额K `9,871.40` 不变
    - 公式三级派生仍正确：F = 原值 − 残值、摊销月数 = 年 × 12、K = F ÷ 月数
  - 数据复原并以 `--diff`「无漂移」为证
  - _Requirements: 4.3, 6.2_

- [x] 9. 批 3+ 规划（不在本轮执行，只产出可执行清单）

  - 用 Task 2 探针对 `confirmed_violation` 剩余项按循环分组，产出批次表
    （循环 / 文件数 / 处数 / 是否与 active spec 冲突）
  - 🔴 逐项复核 `ambiguous` 清单并写入 `EXPLICIT_OVERRIDES`（带 evidence），
    使 `ambiguous` 收敛到 0
  - 高密度文件优先甄别：`h2/impairment/H2TabRecoverable.vue`(21) ·
    `g5-…/G5TabDisclosureListed.vue`(20) · `j1/analysis/J1TabIndustryCompare.vue`(20) ·
    `f2/analysis/F2TabOverallAnalysis.vue`(19) · `f2/core/F2TabDisclosureListed.vue`(19) ·
    `g5-…/G5TabDisclosureSOE.vue`(19) · `g5-…/G5TabLeaseAmortization.vue`(19) ·
    `h3/impairment/H3TabRecoverable.vue`(19) · `i2/impairment/I2TabRecoverable.vue`(19) ·
    `d4/analysis/D4TabProductMargin.vue`(18)
    —— 其中 `J1TabIndustryCompare` / `D4TabProductMargin` 预判多为比率列（反向样本）
  - 与 active spec 的冲突面标注：涉及 E1/K1/L/M/N 等正在推进的循环时登记「待该 spec 收口后处理」
  - _Requirements: 4.1, 4.5_

- [x] 10. CI 挂载与收口

  - `governance-checks.yml` 新增 blocking job，显式列出跑的文件：
    探针 `--check` + `amountColumnSemantics.spec.ts` + `amountInputColumnTyping.spec.ts`
  - 🔴 改 `governance-checks.yml` 的验收判据用**归因型**（变动落在本 spec 的字节区间内），
    不得用「其他 job 一个都没变」的全局等值 —— 该文件多 spec 并发编辑
  - `git status --porcelain -- <本 spec 产物清单>` 必须无 `??`
  - 清理 `_wip_*` 临时产物（只删本 spec 前缀）
  - 全部批次完成后：探针 `--check` 返回 0（`confirmed_violation` 为空）
  - _Requirements: 6.3, 6.4, 6.5_

## Notes

### 本 spec 的立项证据（2026-08-15 浏览器实测）

I1-10 摊销测算表新增 1 行后填 原值 `1234567.5` / 残值 `50000` / 使用期限 `10`：

| 类别 | 列 | 实际显示 | 判定 |
|---|---|---|---|
| 可编辑 `el-input-number` | 原值 | `1234567.50` | ❌ 金额无千分符 |
| 可编辑 `el-input-number` | 残值 | `50000.00` | ❌ 同上 |
| 可编辑 `el-input-number` | 使用期限(年) | `1000.00` / `10.00` | ✓ 不带千分符 |
| 只读派生 `fmtAmount` | 期初净值F | `1,184,567.50` | ✓ |
| 只读派生 `fmtAmount` | 月摊销额K | `9,871.40` | ✓ |

两条洞察：

1. **旧探针的盲区**：I 循环 Task 18 结论是「`el-input-number :formatter` 命中 0 处，合规」
   —— 而这两个文件用的是 `el-input-number` + `:precision="2"`、**根本没写 `:formatter`**。
   判据应是「金额语义列是否用了非 `WpAmountInput` 的控件」，不是「有没有写 `:formatter`」。
   这是假绿第②源（grep 式守卫只查字符串存在）。

2. **反向边界是「碰巧成立」**：「比率/年限列不带千分符」当前成立的原因是
   `el-input-number` 对**所有**列都不做千分符，而非正确区分了列类型
   ⇒ 一换 `WpAmountInput` 就会把「使用期限 1000 年」渲染成 `1,000.00`。
   现有反向断言在未迁移代码上恒真，**没有区分能力**，必须先建判据再迁移。

### memory 数字修正

memory 记「平台现存 40+ 处 `el-input-number :formatter`」—— **实测 80 处 / 13 文件**，
数字翻倍。且真正的问题面是 **1064 处疑似金额列**（含无 formatter 的），
远大于 formatter 的 80 处。

### 待业务确认（登记，不擅改）

- `使用期限(年)` 的 `:precision="2"` 让年限显示 `10.00`。改 `:precision="0"` 会禁掉
  `2.5 年` 这类录入；源模板是否允许小数年限需业务确认。
  同类问题可能存在于其它「期限/年限」列，Task 9 规划时一并普查。

### 三条执行纪律

1. **不跑前端全量**：1999 files / 4-worker 并发会产出大量资源竞争型 flaky
   （实测报 73 files failed，抽样单独复跑只剩 1 个真红）。按引用关系反查辐射面 + 串行
2. **目标文件为 `M` 时跳过**：并发多会话常态，覆盖他人在途改动的代价远高于晚一轮迁移
3. **不动只读展示金额**：那部分归 `displayPrefs.fmtAmount()` 口径，
   I 循环 Task 18 已收口 16 个 SFC 的 7 种本地 `fmtAmount`
