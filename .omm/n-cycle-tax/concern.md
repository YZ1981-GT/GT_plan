# 关注点 / 已知脆弱处（N 循环）

## 1. 🔴 跨表 dead-key 成片（已修，勿回退）

N 循环 crossSheet 是"消费端读 per-item 键 X、生产端存整行数组 X-rows、per-item 从不写"的重灾区：
- **N2↔N4 计提勾稽三重断裂**：读 `N4-1-{tax}-audited` / `N4-2-{tax}-amount`（从不写）→ 改从 rows 现算；
  总额键命名不一致（`N4-1-total-audited` 实际 `N4-1-audited-total`）；EventBus 载荷 N2 发 `accruals` / N4 读 `items`
- **N5↔N1/N3/N4**：`adjudicationVsCalc` 读 `N5-4-currentTax`/`N5-8-deferredExpense`（从不写）→ 改读 N5-4/N5-8 回填的
  `N5-1-current-tax`/`N5-1-deferred-tax`；`_fetchN1Data` 读 `N1-1-begin-balance`（实际 `N1-1-total-begin`）；
  N1 存 **remark** 字段（读 `remark??conclusion`）；N3 事件发 `change`（非 `periodChange`）

排查通用法：对照消费端读的确切键 vs 生产端写的确切键；存整行数组时 per-item 键从不写；
total 键命名顺序（total-audited vs audited-total）；存 remark vs conclusion 字段；EventBus 载荷字段名/形状两端一致；
按名匹配需归一化（税种名）。

## 2. 🔴 render 策略 tb_balance 列名错（N4/N5）

从"查 trial_balance"模板复制的 render 策略指向 `tb_balance` 却用 trial_balance 列名（`begin_balance`/`standard_account_code`）
→ try/except 吞异常静默返 0 + "TB取数失败"warning（每次渲染触发，用户"老出现"）。
`tb_balance` = opening_balance/closing_balance/account_code；`trial_balance` = standard_account_code/unadjusted/audited。

## 3. 类目发散（N1 中招 4 套）

N1 审定表/明细/上市附注/国企附注曾用 4 套不一致的 CATEGORIES 默认清单 → 审定→附注对不齐、applyAutoFill miss。
**审定表/明细/附注的 CATEGORIES 是同一循环内跨 3+ 组件的隐性契约**，改一处必须同步全部；
修枚举用"源模板新类 + 旧名向后兼容"union（不破坏 keyed-by-taxType/category 的历史存储 + 测试自建数据）。

## 4. 按名匹配的勾稽改名会破坏一致性

N4↔N2 计提勾稽按税种名匹配（`useN4CrossSheet`）→ 改名会破坏内部一致性。
N2 源用"车船牌照税"、N4 源用"车船使用税"本无统一命名 → 曾尝试改名后回退，只加注释"切勿单独改名/改序"。
模块内命名是全局契约，不能单文件改。

## 5. N5-2 结构差异（未修，需 spec）

N5-2 源模板是**有效税率调节表**（审定利润总额 → 按法定税率 → 各调整项 → 所得税费用），
现有 N5-2 渲染"当期/递延分项分解表"（调节表信息已在 N5 附注实现未丢）。
改造属跨前后端 >500 行结构重定义（含导入导出）→ spec 级不擅改。

## 6. N1-5 未确认亏损结构 + 附注未确认节

N1-5 源模板结构（到期年度行/本期数三列/确认与不确认拆分/依据/应纳税所得额来源三选/检查底稿索引）
+ 附注"未确认"一节数据源 → 已立 spec `n1-loss-check-source-alignment`（requirements-first，未实现）。

## 7. N1 是资产但取期末余额，N4/N5 是损益取发生额

N1（1811 递延所得税资产）取**期末余额**（时点），N4（6403）/N5（6801）取**发生额**（期间）。
render 取数与审定回写口径要分清，混用会取错数。
