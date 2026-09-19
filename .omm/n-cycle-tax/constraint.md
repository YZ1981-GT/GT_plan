# 约束（N 循环）

平台通用铁律见 `.omm/d-cycle-sales/constraint.md`。以下为 N 循环附加约束。

1. **跨表 crossSheet 读键必须对照生产端确切键**：存整行数组 `X-rows` 时不能读 per-item `X-{k}`（恒空）；
   计算列（endBalance/audited）须现算不读；total 键命名顺序对齐（audited-total）；
   N1 存 remark 字段（`remark??conclusion`）；EventBus 载荷字段两端一致（items??accruals、change??periodChange）。
2. **render 策略表↔列匹配**：查 `tb_balance` 用 opening_balance/closing_balance/account_code；
   查 `trial_balance` 用 standard_account_code/unadjusted_amount/audited_amount；
   要期初/期末/发生额→tb_balance，要未审/AJE/审定→trial_balance；禁 try/except 把列名错吞成静默返 0。
3. **CATEGORIES 类目是跨组件契约**（审定/明细/上市附注/国企附注同源），改一处同步全部；
   修枚举用"源模板新类 + 旧名向后兼容"union。
4. **按名匹配的勾稽（N4↔N2 税种）不单文件改名**（模块内命名全局契约，改名破坏内部一致性）；
   两端命名分歧用归一化（城建/城市维护建设、车船税/车船牌照/车船使用）。
5. **N1 取期末余额（时点），N4/N5 取发生额（期间）**，render 与回写口径分清。
6. **所得税费用勾稽**：N5 = 当期所得税 + 递延所得税；递延 = ΔN1 − ΔN3；有效税率调节表口径。
7. **暂时性差异 × 适用税率**（默认 25%）→ N1/N3；可抵扣→N1，应纳税→N3。
8. **明细表默认种子**（N1 29 项/N2 13 税种/N3 10 项）空态生效，不覆盖已录数据。
9. **审定表带入**：N1 双期 target 期末（endAje/endRje）；N2/N3 keyed by taxType/category；
   N5 自包含无 composable（currentRow/deferredRow 两行 refs，updateCell 直接 mutate + 调 handleCellChange 持久化）。
