# 上下文：N 循环特有机制

通用机制见 `.omm/d-cycle-sales/context.md` 与 `shared-runtime/`。本文只写 N 特有部分。

## 1. 科目码常量

N1 `'1811'`（递延所得税资产，取期末余额）、N2 `'2221'`（应交税费）、N3 `'2901'`（递延所得税负债）、
N4 `ACCOUNT_CODE_6403='6403'`（税金及附加，取发生额）、N5 `'6801'`（所得税费用，取发生额）。

## 2. N1 双期结构 + 派生披露层

N1-1 审定表是**期初/期末双期**（各未审/账项调整/重分类/审定），按 7 类资产侧暂时性差异
（资产减值准备/可抵扣亏损/内部交易未实现利润/公允价值变动/租赁负债/购入摊销年限小于税法规定的资产/其他）。
N1 有独立派生层 `useN1DisclosureSource`（用同一 engine 重算不落库的 computed 列供披露）。

## 3. N2 应交税费的多税种测算

N2-1 审定表 13 类标准税种（增值税/企业所得税/城建税/教育附加/地方教育附加/印花税/房产税/
城镇土地使用税/车船税/土地增值税/资源税/矿产资源补偿费/代扣代缴个税）。
N2-2 明细有增值税/房产税/土地增值税等专项测算表。

## 4. N5 有效税率调节表（核心）

`所得税费用（N5）= 当期所得税 + 递延所得税`；有效税率调节：
会计利润 × 法定税率 → +不可抵扣费用 + 免税收入 + 税率差异 + 未确认递延的亏损 + 以前年度汇算清缴 = 实际所得税费用。
N5-2 曾误做成"当期/递延分项分解表"，源模板实为**有效税率调节表**（结构差异，重建属 spec 级未做）。

## 5. 跨表 dead-key 修复（N 循环系统性）

N 循环 crossSheet 曾有成片 dead-key（消费端读 per-item 键 X，生产端存整行数组于 X-rows，per-item 从不写）：
- **N2↔N4 计提勾稽**（税金及附加费用确认 = 应交税费计提）：读 `N4-1-{tax}-audited` 从不写 →
  改从 `N4-1-rows`/`N4-2-detail-rows` 现算；总额键命名对齐（`N4-1-audited-total` 非 `N4-1-total-audited`）；
  税种名归一化（城建税/城市维护建设税、车船税/车船牌照税/车船使用税）
- **N5↔N1/N3/N4**：`adjudicationVsCalc` 读 N5-4/N5-8 实际回填的 `N5-1-current-tax`/`N5-1-deferred-tax`；
  `_fetchN1Data` 读 `N1-1-total-begin`/`N1-1-total-audited`（N1 存 **remark** 字段，读 `remark??conclusion`）；
  N3 事件发 `change` 而非 `periodChange`（兼容 `change??periodChange`，否则递延税负债本期变动恒 0）

## 6. N4↔N2 EventBus 载荷字段名

N2 发 `{accruals:[{tax,amount}]}` vs N4 读 `payload.items` → N4 handler 兼容 `items??accruals` + `accrual??amount`。

## 7. 明细表默认种子

N1-2/N2-2/N3-2 起步空表 → `seedDefaultRows()` + "预置源模板常见项目/税种"按钮（空态生效）：
N1 29 项 + 类别映射、N2 13 类标准税种、N3 10 项 + category 映射 N3-1 五类。

## 8. 审定表带入调整

N1（1811 资产 debit，双期 target 期末 endAje/endRje）/ N2（2221 负债 credit，updateRow taxType 字符串键）/
N3（2901 负债 credit，category 字符串键）/ N4（6403 损益 debit，updateCell rowKey）/
N5（6801 损益 debit，自包含无 composable，currentRow/deferredRow 两行 refs）。

## 9. render 策略 tb_balance 列名（N 循环踩过）

N4/N5（损益）render 曾从"查 trial_balance"模板复制却指向 `tb_balance`，列名全错（`begin_balance` 应 `opening_balance`、
`standard_account_code` 应 `account_code`），包在 try/except 里静默返 0 + 打"TB取数失败"warning（每次渲染都触发）。
`tb_balance` 列 = opening_balance/closing_balance/account_code/debit_amount/credit_amount；
`trial_balance` 列 = standard_account_code/unadjusted_amount/aje_adjustment/audited_amount。
要期初/期末/发生额查 tb_balance；要未审/AJE/审定查 trial_balance。
