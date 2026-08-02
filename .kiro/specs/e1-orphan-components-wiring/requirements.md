# Requirements Document

## Introduction

E1 货币资金循环有 **8 个组件已按源模板写好、但从未被任何宿主渲染**（约 225 KB），
另有 1 个只被这些孤儿消费的壳组件（`E1IpoSheetChrome.vue`）连带死亡。
后果不是「功能缺失」而是**用户看到的是降级版底稿**：

| 源模板 sheet | 当前渲染 | 已写好但闲置 |
|---|---|---|
| E1-19 企业信用报告信息与账面核对记录 | `E1TabCreditReport`（5 列扁平表，E1-18 的组件） | `E1TabCreditCheck`（五小节：注册资本出资人对照 / 信贷类别征信vs账面 / 不一致时点调节 / 担保事项 / 关联关系企业） |
| E1-26 现金交易分析 | `E1TabIpoSpecial`（`COLUMN_CONFIG` 驱动的单张动态行表） | `E1TabCashTxnAnalysis`（月度总体 / 合理性 / 金额分布 / 客户供应商概要） |
| E1-29 银行账户分析 | 同上 | `E1TabBankAccountAnalysis`（清单+开户地 / 多年指标 / 红旗提示） |
| E1-30 存款规模与利息收入匹配性 | 同上 | `E1TabDepositInterestDaily`（日余额×年利率/360、按月分页、E1-15 联动） |
| E1-31 银行流水双向核对 | 同上 | `E1TabBankFlowReconcile`（月度汇总 / 账→流 / 流→账 / 流水 OCR / 覆盖率） |
| E1-32 董监高关键岗位资金流水核查 | 同上 | `E1TabKeyPersonFlow`（关联方流水 + OCR + 与 E1-31 联动） |
| E1-21/E1-22 截止测试 | `E1TabCutoffTest`（无 OCR 入口） | `E1CutoffOcrConfirmDialog` |
| E1-23 大额收支检查 | `E1TabLargeCheck`（无 OCR 入口） | `E1LargeCheckOcrConfirmDialog` |

判定依据：扫全仓 4978 个候选消费方（排除 `components.d.ts` 自动注册与 `__tests__`）零命中。

**接线是低风险的**：6 个 sheet 组件的 props 签名与宿主现有传参**完全一致**
（`wpId` / `projectId` / `allResponses` / `saveImmediate` / `debouncedSave` / `isReadonly`
/ `sheetName?` / `bsDate?`），且 5 个 IPO composable **已内建 legacy 键回退**
（`E1-ipo-E1-2X-rows` / `E1-ipo-audit-note-E1-2X` / `E1-ipo-audit-conclusion-E1-2X`
+ 共享 `E1-ipo-applicable`）→ 切换宿主分发不丢已录数据。

本 spec 同时收口三项与接线同一批文件强相关的存量欠账（不扩大到 E1 全域）：
接线文件里的 `el-input-number :formatter` 空操作、5 个 Tab 的 AI/复核空洞、
披露 Tab 缺变体适用性门控；并新增**平台级守卫**防止这类漂移再发生
（E1 一次攒了 8 个孤儿，说明没有任何机制拦它）。

## Requirements

### Requirement 1: 孤儿 sheet 组件接线

**User Story:** 作为审计助理，我打开 E1-19 / E1-26 / E1-29 / E1-30 / E1-31 / E1-32 时，
应看到与源模板结构一致的多小节底稿，而不是一张通用扁平表。

#### Acceptance Criteria

1. WHEN 当前 sheet 为 `E1-19` THEN 宿主 SHALL 渲染 `E1TabCreditCheck`，
   且 `E1-18` 仍渲染 `E1TabCreditReport`（两者不得再共用同一组件）
2. WHEN 当前 sheet 为 `E1-26` / `E1-29` / `E1-30` / `E1-31` / `E1-32` THEN 宿主
   SHALL 分别渲染对应的专属组件
3. WHEN 当前 sheet 为 `E1-27` / `E1-28` THEN 宿主 SHALL 继续渲染 `E1TabIpoSpecial`
   （这两张无专属组件，通用表是**有意保留**的正确形态）
4. WHEN 宿主向专属组件传参 THEN 传入的 prop 名 SHALL 全部存在于该组件的 `defineProps`
   （宿主传不存在的 prop = 静默失效，四层验证全查不出）
5. WHEN 专属组件声明了必填 prop THEN 宿主 SHALL 确实传入该 prop
6. WHEN 接线完成 THEN `E1IpoSheetChrome` SHALL 至少被一个可达组件消费（不再是传递性死代码）

### Requirement 2: 数据零丢失（legacy 键迁移）

**User Story:** 作为已在通用表里录过 E1-26~E1-32 数据的审计师，切换到新组件后我的数据不能消失。

#### Acceptance Criteria

1. WHEN 项目已有 `E1-ipo-E1-2X-rows` 落库数据且新 pack 键为空 THEN 专属 composable
   SHALL 从 legacy 键读出并展示
2. WHEN 项目同时有 legacy 键与新 pack 键 THEN SHALL 以**新 pack 键为准**（用户已在新组件录过）
3. WHEN 专属组件读取审计说明/结论 THEN SHALL 按 `新键 → legacy 键 → 空串` 的优先级回退
4. WHEN 用户在新组件里编辑 THEN 写入 SHALL 只落新 pack 键，**不得回写 legacy 键**
   （否则两套键长期双真源）
5. WHEN 共享的「是否启用 IPO 程序」开关被读写 THEN 两套组件 SHALL 使用同一个
   `E1-ipo-applicable` 键（切换组件后开关状态不变）

### Requirement 3: 截止测试 / 大额收支 OCR 链路补齐

**User Story:** 作为审计助理，我在 E1-21/E1-22 截止测试与 E1-23 大额收支检查里
可以上传凭证影像并 OCR 识别后确认填入，而不是逐格手敲。

#### Acceptance Criteria

1. WHEN 用户在 E1-21/E1-22 上传凭证影像 THEN 系统 SHALL 调用后端 OCR 端点并把
   识别结果交给 `E1CutoffOcrConfirmDialog` 供用户确认
2. WHEN 用户在 E1-23 上传收支单据影像 THEN 系统 SHALL 调用后端 OCR 端点并把
   识别结果交给 `E1LargeCheckOcrConfirmDialog`（含 `side: 'debit' | 'credit'` 区分）
3. WHEN 用户在确认弹窗里改动字段后确认 THEN 系统 SHALL 用**用户确认后的值**写入行，
   而非 OCR 原值
4. WHEN OCR 识别置信度低或字段缺失 THEN 弹窗 SHALL 可见地提示，且 SHALL NOT 静默填 0
5. WHEN OCR 端点失败 THEN SHALL 提示用户并保留手工录入能力，SHALL NOT 阻断底稿编辑
6. WHEN 后端新增这两个 OCR 端点 THEN 其请求/响应形态 SHALL 与既有 4 个 E1 OCR 端点
   （`account-list` / `commit` / `credit` / `statement`）一致

### Requirement 4: 接线文件的金额控件收口

**User Story:** 作为审计师，新接入页面里的可编辑金额格应显示千分符，而不是一长串数字。

#### Acceptance Criteria

1. WHEN 本 spec 接线的文件含可编辑**金额**格 THEN SHALL 使用 `WpAmountInput`，
   SHALL NOT 使用 `el-input-number :formatter`（EP 2.13.6 无该 prop = 空操作）
2. WHEN 某格是折算率 / 汇率 / 利率 / 比例 / 面值 / 张数 / 笔数 / 年度 THEN
   SHALL NOT 套用 `WpAmountInput`
3. WHEN 本 spec 完成 THEN `E1_LEGACY_FORMATTER_BUDGET` 中被接线文件对应的条目
   SHALL 归零并从预算表移出（守卫要求「已修好必移出」）
4. WHEN 只读金额被渲染 THEN SHALL 走 `displayPrefs.fmtAmount()`（store 成员，
   不是 `@/stores/displayPrefs` 的模块命名导出）

### Requirement 5: AI 辅助与复核补齐

**User Story:** 作为审计助理，每个需要写文字的区域都应有 AI 起草与复核入口。

#### Acceptance Criteria

1. WHEN Tab 内存在审计说明 / 审计结论类文本域 THEN 该文本域 SHALL 配 AI 生成按钮
2. WHEN AI 按钮被点击 THEN SHALL 调用 `POST /api/workpapers/{wpId}/ai/generate-text`，
   请求体 `context` SHALL 为 `dict[str, str]`（传字符串必 422 且被 catch 静默吞）
3. WHEN 新增 AI section THEN SHALL 同时登记后端 `_SUPPORTED_SECTIONS` 与 `_SECTION_PROMPTS`，
   且每条 prompt SHALL 写明源模板口径并含「不得虚构」约束
4. WHEN Tab 内有 section 标题 THEN AI 与复核按钮 SHALL 右对齐在该标题同一行
5. WHEN 底稿处于只读态 THEN AI 与复核按钮 SHALL 禁用

### Requirement 6: 披露 Tab 变体适用性门控

**User Story:** 作为在国企项目上工作的审计师，我打开上市披露 Tab 时应直接看到
「当前项目不适用」，而不是填完一遍才被服务端拒绝。

#### Acceptance Criteria

1. WHEN 项目适用准则不含 `listed*` 且当前 Tab 变体为 `listed` THEN Tab SHALL 渲染
   「当前项目不适用上市附注披露」提示页，SHALL NOT 渲染录入区
2. WHEN 项目适用准则不含 `soe*` 且当前 Tab 变体为 `soe` THEN 同理
3. WHEN 变体不适用 THEN 手动同步按钮与自动同步 SHALL 一律不触发任何写入
4. WHEN 项目适用准则解析不出（空数组）THEN SHALL **放行**（fail-open，不误杀）
5. WHEN 门控生效 THEN SHALL 与服务端 `detect_standard_conflict` 的判定口径一致
   （只判 entity 维度，scope 差异放行）

### Requirement 7: 接线 sheet 的公式预设补齐

**User Story:** 作为审计助理，四表入库后新接入的页面也应能自动带出可取数的部分。

#### Acceptance Criteria

1. WHEN 存在 `E1-20 应计利息测算` THEN 公式预设 SHALL 提供其可由四表推导的锚点
   （银行存款余额），无法推导的项 SHALL 写 `PLACEHOLDER` 并在描述里写明来源
2. WHEN 存在 `E1-15 利息收入月度分析` THEN SHALL 补预设块（现有组件但零预设）
3. WHEN 新增预设条目 THEN 其 `account_codes` 与公式引用的科目 SHALL 属于本循环
   报表行（`BS-002 = TB('1001')+TB('1002')+TB('1012')`）解析出的科目集合
4. WHEN 新增预设块 THEN 其 `sheet` 字段 SHALL 与源 xlsx 的 tab 名逐字一致
5. WHEN 明细类 sheet 新增预设 THEN SHALL NOT 使用 `WP()` 引用审定表（防成环）

### Requirement 8: 平台级孤儿组件守卫

**User Story:** 作为平台维护者，我需要一条守卫在「组件写好却没接线」时立刻打红，
而不是几个月后靠人工复盘才发现。

#### Acceptance Criteria

1. WHEN 运行守卫 THEN 它 SHALL 扫描各循环组件目录下的 `*Tab*.vue`，
   对每个组件判定是否存在**可达消费方**
2. WHEN 判定消费方 THEN SHALL 排除 `components.d.ts`（自动注册不等于使用）
   与 `__tests__`（测试引用不等于渲染）
3. WHEN 某组件无可达消费方 THEN 守卫 SHALL 失败，除非它在 allowlist 中登记且写明理由
4. WHEN 消费链存在传递性死亡（消费方本身是孤儿）THEN 守卫 SHALL 同样判定为孤儿
5. WHEN 守卫运行 THEN SHALL 含反向自检（构造一个替身孤儿必被识别），防止扫描逻辑空转
6. WHEN allowlist 中某条目已接线 THEN 守卫 SHALL 要求把它移出

### Requirement 9: 零回归与实测

**User Story:** 作为平台维护者，我需要确认接线没有打断 E1 既有 22 张 sheet 的任何一张。

#### Acceptance Criteria

1. WHEN 本 spec 改动落地 THEN E1 相关既有测试 SHALL 全绿（预存在失败基线除外，须逐条列明）
2. WHEN 改动落地 THEN 每个被改文件的 Vite transform SHALL 返回 200
3. WHEN 浏览器实测 THEN 6 个新接线 sheet SHALL 全部挂载、零 console error
4. WHEN 浏览器实测 THEN SHALL 验证 legacy 键迁移：先用通用表录数据、切换后数据仍在
5. WHEN 实测写库 THEN SHALL 先快照、后按 md5 逐字节复原；不可复原字段 SHALL 如实记录
6. WHEN 本 spec 完成 THEN 会话产生的 `tmp_*` 诊断产物 SHALL 清理干净

## Glossary

- **孤儿组件**：文件存在、编译通过、但没有任何可达宿主渲染它的 Vue 组件
- **legacy 键**：通用 `E1TabIpoSpecial` 时代的持久化键（`E1-ipo-E1-2X-rows` 等）
- **pack 键**：专属 composable 的结构化持久化键（`E1-cash-txn-pack` 等）
- **传递性死亡**：组件本身有消费方，但消费方是孤儿 → 它同样不可达
