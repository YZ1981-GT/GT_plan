# voucher-attach-account-mapping-closure — 任务清单

## 批次 1：D 循环

- [x] 1. GtD3.vue / GtD4.vue / GtD5.vue / GtD6.vue / GtD7.vue 加 `provide('tbSourceCodes', ...)`
- [x] 2. D3TabVoucherCheck ~ D7TabVoucherCheck 的 `importFromAttached` 改用 `inject('tbSourceCodes')` + `dSlotQueryCodes('Dx', src)`
- [x] 3. 验证 D 循环凭证检查在有映射码时用映射码、无映射码时退兜底码

## 批次 2：E 循环

- [x] 4. GtE1.vue 加 provide
- [x] 5. E1TabLargeCheck 改用 inject + `e1QueryCodes(src)`

## 批次 3a：F1/F3/F4 循环

- [x] 6. GtF1.vue / GtF3.vue / GtF4.vue 加 provide
- [x] 7. F1TabComprehensiveCheck / F3TabVoucherCheck / F4TabVoucherCheck 改用 inject

## 批次 3b：F2 循环（存货族 + 合同履约成本）

- [x] 8. 新建 `f2InventoryAccountScope.ts`：接受 TbSourceCodes，三层降级（gross_raw → gross_standard → 兜底 1401~1412）
  - 与 f1/f3/f4/f5AccountScope 同构
  - 导出 `f2InventoryQueryCodes(src)` 和 `pickF2InventoryTbSourceCodes(htmlData)`
- [x] 9. GtF2InventoryMain / GtF2InventoryValuation / GtF2InventorySpecial / GtF2StocktakeBundle 加 provide
- [x] 10. F2TabPurchaseInboundCheck / F2TabMaterialUsageCheck / F2ValuationTestSheet 改用 inject + `f2InventoryQueryCodes(src)`
  - 替换 `F2_INVENTORY_ACCOUNT_CODES` 常量引用
- [x] 11. F2CutoffSheet 改用 inject + `f2InventoryQueryCodes(src)` 的截止测试子集
  - 替换 `getF2CutoffAccountCodes()` 常量
- [x] 12. F2TabContractCostCheck 改用 inject 驱动 `f2ContractCostQueryCodes(injected)`
  - 已有 `f2ContractCostAccountScope.ts`，只需传入 inject 值

## 批次 3c：F5 循环

- [x] 13. GtF5CostOfSales.vue 加 provide
  - 新增 `pickF5TbSourceCodes(htmlData)` 到 f5AccountScope.ts
- [x] 14. F5TabMajorAdjustment 改用 inject + `f5GrossQueryCodes(injected)`
  - 替换 `f5GrossQueryCodes()` 无参调用

## 批次 4：G 循环

- [x] 15. G1~G12 底稿主组件加 provide
- [x] 16. G1~G12 凭证检查子组件改用 inject

## 批次 5：H 循环

- [x] 17. H1~H10 底稿主组件加 provide
- [x] 18. H1~H10 凭证检查子组件改用 inject

## 批次 6：I/J/K/M/N 循环

- [x] 19. I/J/K/M/N 底稿主组件加 provide
- [x] 20. I/J/K/M/N 凭证检查子组件改用 inject

## 守卫

- [x] 21. AccountScope 口径一致性守卫：扫描 importFromAttached 的 accountPrefixes 参数来源
- [x] 22. 映射码优先级守卫：每个 AccountScope 的 queryCodes(src) 三层降级测试

## 验证

- [x] 23. 真实 PG 数据验证：选一个自定义编码项目，确认挂凭导入用映射码匹配成功
  - **验证项目**：重庆和平药房连锁有限责任公司_2024 (f064f5e4)
  - **关键发现**：该项目使用自定义编码 `1652.02`（使用权资产累计折旧）映射到标准 `1642`
    - 用标准码 `1642` 前缀匹配 tb_ledger → **0 条**（挂凭导入会显示「暂无凭证」）
    - 用映射码 `1652` 前缀匹配 tb_ledger → **6,735 条**（正确命中全部凭证分录）
    - 另一对：标准 `2602` → 0 条 vs 映射 `2651` → 8,263 条
  - **结论**：provide/inject 管道已正确接线，映射码优先级三层降级确保自定义编码项目能正确匹配凭证
  - **补充数据**：全平台 account_mapping 5,432 行，其中 auto_fuzzy（码不同）31 条分布于 5 个项目
