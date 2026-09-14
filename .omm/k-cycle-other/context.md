# 上下文：K 循环特有机制

通用机制见 `.omm/d-cycle-sales/context.md` 与 `shared-runtime/`。本文只写 K 特有部分。

## 1. 科目码常量在各 `useK{n}FormData.ts` 顶部

K1 1221（+坏账 1231）、K2 1231、K3 2241、K4 2245、K5 2701、K6 1481 资产 + 2605 负债、
K7 2401、K8 6601、K9 6602、K10 6117、K11 6701、K12 6301、K13 6711。
损益类（K8/K9/K10/K11/K12/K13）**取发生额**，回写 `PUT /trial-balance/writeback`。

## 2. 凭证检查表复用 `useK1VoucherCheck`（K 循环范式提供者）

K1-12（其他应收款凭证检查）是 gold 标准：认定目标 + 样本选取标准与规模 + 双凭证级测试表
（本期发生额 / 期后收款）+ 检查比例表 + 抽凭引擎（account-code=1221）。
`useK1VoucherCheck` 被 K3-7（2241）、K5-7（2701）、K7-5（2401）、K8-8（6601）、K9-8（6602）复用，
额外字段（staffCount/approver/期后付款等）靠 `...r` 展开透传，核对标签经 `checkLabels` 参数按科目定制
（K9 用「⑤费用分类正确」而非 K1 的「债务人核对」）。

## 3. K8/K9 是费用截止测试的主战场

`useK8Cutoff` / `useK9Cutoff`（`ACCOUNT_CODE_6601/6602`，`DEFAULT_THRESHOLD_DAYS=5`）：
- 从序时账取数走 `POST /sampling/cutoff-test`（历史调不存在的 `ledger/cutoff-samples` 恒 404，已修）
- 显式传 `cutoff_date`（否则后端按 year-12-31 推导，期中审计误判）
- 跨期判定用自然月比较（K8/K9 的 `isCrossPeriod`，与 I2/I6 的截止日 XOR 口径不同——**两种语义都是 spec'd，不能强行统一**）
- 双侧证据缺失结论"证据不完整"；跨期 → A13 push（K8-6/7、K9-6/7 各自 `a13:push-misstatement`）

## 4. K8/K9 从序时账按月取数

`expenseLedgerMonthlyPull.ts`（纯前端游标分页拉 `/ledger/entries/{6601|6602}` 按 account_name × 月聚合借-贷）
→ K8-2 / K9-2 明细表「从序时账取数」。K13 也复用（6711）。

## 5. K11 是"减值汇总科目"，18 类 canonical + 来源映射

`useK11Adjudication` 默认 18 类资产侧减值（合同资产/存货跌价/合同取得成本/合同履约成本/持有待售/
其他权益工具投资/其他非流动金融资产/长期股权投资/投资性房地产/固定资产/工程物资/在建工程/
生产性生物资产/油气资产/使用权资产/无形资产/商誉/其他），来源 sourceWp 映射各资产底稿；
`normalizeImpairmentCategory` 归一化匹配（"存货跌价准备"↔"存货跌价损失"）。
K11-2 有减值准备 rollforward（对应科目 + 期初/计提/转回/转销/期末 + 本期计入损失）。
**边界**：K11（6701 资产减值）≠ G14（6702 信用减值，仅金融资产）。

## 6. 「从集中登记带入调整」在 K 循环全覆盖

用共享 `useAdjudicationBringIn`（`subjectPrefix` + `direction` 定净发生额符号）+ `AdjudicationBringInDialog`
（逐笔选目标分类行，`guessTargetRowKey` 默认智能猜，解决科目↔分类歧义）：
- 损益单科目（K8/K9/K10/K11/K12/K13）：`direction` 定 credit=贷−借 / debit=借−贷
- 资产负债多分类（K2/K3/K4/K5/K7）：直接接
- 双科目（K6=1481+2605）：两独立 helper 实例
- 双维度同总额（K3=性质+账龄）：带入主维度 + 既有交叉校验引导
- roll-forward 宽表（K1=应收原值 1221 + 坏账准备 1231）：K1AdjWideTable 期末段有 AJE/RJE 列，两独立 helper 实例

## 7. 附注（权威 `note_template_variant_matrix`）

- K1 五、8 / 八、9（**其他应收款节，含 G2 应收利息 / G3 应收股利并入**）
- K5 CAS13 或有事项、K6 CAS42 孰低、K7 CAS16 政府补助（各有源模板专属结构）
- K11 三、资产减值损失 / 八、74；K12 三、营业外收入 / 八、77；K13 三、营业外支出 / 八、77
- 损益类 listed 是关键词标题（三、…），DB 可能截断 → `resolveSectionInList` 模糊→精确
- **K12/K13 反向跳转按钮放 header-actions / section-actions**（无同步按钮，走 EventBus/审定表取数）

## 8. 双模式「拉取成功」范式

各科目 `useK{n}DualMode`（照 useF2DualMode）：切 OnlyOffice 前先 GET `onlyoffice-config`（**带 project_id 参**），
config 拉取成功才切，失败回退 html。主入口 el-segmented 用 `:model-value` + `@change`（**禁 v-model**，
v-model 抢先改值使 switchMode 首行短路 → config 门失效）。目录 sheet 从 OO 分支排除。

## 9. 目录页已按 E1 标准重建

各 `K{n}TabIndex` = 目录卡（标题 + 复核 + 编制/使用手册按钮 + 进度条 → 跨表结论口径看板 → 编制提示）
+ `GtBArchitectureTree` 4 阶段泳道 + 本循环底稿 grid（`loadCycleWorkpaperCards`，源模板 canonical 清单）。
主入口 header 工具栏（AI 复核 + 双模式）在目录 sheet 隐藏（`currentSheet !== 'Kx'`）。
每科目独立 `handbooks/{preparation,usage}.md` + `KxPreparationHandbookDialog`。
