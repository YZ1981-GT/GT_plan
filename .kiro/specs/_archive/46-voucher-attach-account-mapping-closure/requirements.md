# voucher-attach-account-mapping-closure — 需求文档

## 背景

当前 58 个凭证检查组件已接入「从序时账挂入导入」功能（pullSamplesForWorkpaper）或抽凭引擎（GtVoucherSamplingEngine），但科目前缀匹配全部使用**兜底标准码**（如 D2 用 1122、E1 用 1001/1002/1012、F2 用 1401~1412）。

问题：不同企业的科目编码体系不同，科目映射规则（ccount_mapping）已将企业自定义编码映射到标准报表科目，但凭证检查子组件**拿不到映射后的 	b_source_codes**，导致：
- 企业用自定义编码（如 110201 代替 1122）时，挂凭导入的科目前缀匹配**命中 0 条**
- 审计师看到「暂无挂入本底稿的序时账凭证」，但实际已挂入——是匹配不到而非没数据

这是平台通用适配性的核心问题。科目映射规则是全平台共用的基础设施（国企/上市转换、合并/单体附注映射、报表公式取数、四表查询等模块都依赖它），凭证联动必须与这些模块保持同一数据来源。

## 需求

### R1 — 映射码传递（provide/inject）

1.1 每个底稿主组件（如 GtD3.vue、GtE1.vue、GtF2InventoryValuation.vue 等约 40 个）在 render-config 请求成功后，通过 provide('tbSourceCodes', tbSourceCodes) 注入映射后的科目码。

1.2 每个凭证检查子组件（58 个已接入的）通过 inject('tbSourceCodes', null) 取到映射码后，调用 xxxQueryCodes(injectedSrc) 获取该企业的真实科目前缀（而非兜底码）。

1.3 未注入时（inject 返回 
ull）退到兜底码——向后兼容，不破坏当前行为。

### R2 — AccountScope 统一消费口径

2.1 pullSamplesForWorkpaper 的 ccountPrefixes 参数和 GtVoucherSamplingEngine 的 :account-code prop 必须来自 AccountScope 的 queryCodes(src) 调用，src 为 inject 得到的 	b_source_codes。

2.2 禁止在凭证检查组件内硬编码科目前缀（如 ['1122']、F2_INVENTORY_ACCOUNT_CODES），必须走 AccountScope 函数。

2.3 **F2 存货族**：F2_INVENTORY_ACCOUNT_CODES 常量（1401~1412）当前被 3 个子组件直接引用作为抽凭科目，需改走 inject → AccountScope 三层降级。F2 截止测试（F2CutoffSheet）使用 getF2CutoffAccountCodes() 常量也需改为 inject 驱动。

2.4 **F2 合同履约成本**：F2TabContractCostCheck 已有 2ContractCostQueryCodes()（兜底空串，无码时禁用抽凭），但当前无参调用，需改为 2ContractCostQueryCodes(injected) 走 inject 驱动。

2.5 **F5 营业成本**：F5TabMajorAdjustment 使用 5GrossQueryCodes() 无参兜底，需改为 5GrossQueryCodes(injected) 走 inject 驱动。

### R3 — 覆盖率守卫

3.1 新增测试：验证每个凭证检查组件的 importFromAttached / GtVoucherSamplingEngine 的科目前缀与对应 AccountScope 的 queryCodes() 一致（不重不漏）。

3.2 新增测试：验证有 	b_source_codes 注入时，queryCodes(src) 优先返回映射码、src 为 null 时返回兜底码。

### R4 — 适用性验证

4.1 用真实 PG 数据验证：选择一个科目编码与标准不同的项目（如首汽租车），确认挂凭导入能通过映射码正确匹配凭证分录。
