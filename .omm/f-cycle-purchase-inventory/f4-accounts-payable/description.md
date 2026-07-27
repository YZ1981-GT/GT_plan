# F4 应付账款（2202）

componentType `f4-accounts-payable`，主入口 `GtF4AccountsPayable.vue`，后端 `_f4_accounts_payable.py`。
负债类，重点认定是**完整性**（是否存在未入账应付）。

## Tab 组成（`f4/`）

| 组件 | 作用 |
|---|---|
| `F4TabAdjudication` + `F4AdjudicationTable` | 审定表（按性质 + 按账龄双维度），TB 2202 核对与回写 |
| `F4TabDetail` | 供应商明细 + 账龄（**扁平 4 字段**，见 concern） |
| `F4TabAdjustment` | 调整分录 |
| `F4TabSubstantiveAnalysis` | 实质性分析（波动、占比） |
| `F4TabLongOutstanding` | 长期挂账应付（CAS16 转销评估、处理结论） |
| `F4TabUnrecordedCheck` | **未入账应付搜索**（完整性程序，F3 无对应） |
| `F4TabSupplierFinancing` | 供应商融资安排（应付账款融资/反向保理，披露关注） |
| `F4TabRelatedParty` | 关联方应付 |
| `F4TabVoucherCheck` + Table/Dialog | 凭证级检查（引导弹窗） |
| `F4TabDisclosureListed` / `F4TabDisclosureSOE` | 附注披露（listed **五、37**，权威 `note_template_variant_matrix`） |
| `F4ImportExportToolbar` | 统一导入导出 ▾ |

## 关键机制

- **审定表回写**：`useF4Adjudication` 回写 2202 + `eventBus.emit('substantive:adjudicated', {wpCode:'F4', accountCode:'2202'})`
  + `window` 事件 `f4:writeback-trial-balance`（新旧双通道，经 `crossWpEventBridge` 桥接）
- **附注文本联动**：`useF4DisclosureListed` 发 `disclosure:note-text-updated`（带 `accountCode:'2202'` + `sectionIds:['五、37']`）→
  `useNoteRefresh` 定向刷新当前附注节；SOE 版发同事件（`type:'soe'`）
- **账龄**：自有 5 固定 rowKey + 明细扁平 4 字段，**F 循环也是全平台唯一未统一到 `useAgingConfig` 的循环**（详见 concern 与 spec）
- **期后付款取数**：可从次年序时账 2202 借方按供应商名归集（`importPostPaymentFromLedger` 范式）

## 与其他循环的关系

- 采购—付款：F2 存货入库 → F4 应付 → E1 付款；F3 以票抵账
- 长期挂账转销 → K12 营业外收入 / 其他应付款重分类
- 未入账应付 → A13 未更正错报（完整性错报）
