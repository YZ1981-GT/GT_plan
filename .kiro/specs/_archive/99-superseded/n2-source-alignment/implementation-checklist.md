# N2 应交税费底稿源模板对齐 — 完整实现清单

> 本文件记录 2026-07-23 会话分析确定的全部改动，因 context compaction 未落盘。
> 新会话按此清单逐文件执行即可。

## 改动总览

- 1 后端 render 策略
- 1 composable (useN2DualMode thin wrapper)
- 14 前端组件 (主入口 + 6 core + 3 inspection + 5 calc)
- 全部 Vite transform 200 验证通过（会话内）

## 文件1: composables/useN2DualMode.ts — 完全重写

删除原有内容(Task 3.3旧版本,106行自有OO健康检查)。
新建 thin wrapper (~30行):

```ts
import { type Ref } from 'vue'
import { useWorkpaperEntryDualMode, type WorkpaperRenderMode } from './useWorkpaperEntryDualMode'

export type N2RenderMode = WorkpaperRenderMode

export function useN2DualMode(options: {
  currentSheet: Ref<string>
  sheetName: Ref<string>
  reloadAllResponses: () => Promise<void>
}) {
  return useWorkpaperEntryDualMode({
    reloadAllResponses: options.reloadAllResponses,
    resolveOoSheetName: () => options.sheetName.value?.trim() || options.currentSheet.value || 'N2',
  })
}
```

## 文件2: GtN2TaxesPayable.vue — 主入口双模式修复

- import useN2DualMode + type N2RenderMode
- 删除假 dualMode 对象 (line~280-288)
- 新增: `const dualMode = useN2DualMode({currentSheet, sheetName: computed(()=>props.sheetName||''), reloadAllResponses: selfLoad})`
- 新增: renderMode computed (get/set proxy switchMode)
- 新增: renderModeOptions computed (OO项disabled when !ooAvailable)
- 新增: onOoFallback → switchMode('html')
- 模板: toolbar segmented绑renderMode, OO组件加:key+@fallback

## 文件3: n2/core/N2TabAdjudication.vue — 完全重写14列

源结构: 项目 + 期初数(未审/账项调整/重分类/审定auto) + 期末数(同4列) + 变动(未审变动额/率 + 审定变动额/率) + 原因分析

关键:
- 嵌套el-table-column分组表头
- 公式: beginAudited=beginUnadj+beginAje+beginRje, endAudited同理
- 变动: unadjChange=endUnadj-beginUnadj, rate=change/begin
- >30%黄字 >50%红字
- 底部试算平衡勾稽行(TB 2221期末 vs 审定合计)
- TB回写 + GtIndexChip N4联动
- 审计说明+结论(AI真回填)
- item_id: N2-1-adjudication-rows (JSON array)
- 恢复兼容旧字段名

## 文件4: n2/core/N2TabDetail.vue — 完全重写16列

源结构: 项目/税率/未审(期初C/应交D/已交E/期末F=C+D-E)/期初调整G/账项调整(应交I/已交J)/重分类(应交K/已交L)/审定(期初M=C+G/应交N=D+I+K/已交O=E+J+L/期末P=M+N-O)/备注

关键:
- 嵌套表头
- 公式列灰底auto
- 13固定税种+可新增/删
- 统计摘要
- seedFromN21(): 无数据时从N2-1 seed未审期初
- item_id: N2-2-detail-rows + N2-2-note + N2-2-conclusion

## 文件5: n2/core/N2TabAdjustment.vue — 补4列+类别

- 补列: reportItem/noteItem/indexNo/remark
- "类型"→"类别" el-select(报表调整/账项调整/其他)
- 列名优化: 调整事项说明/借方调整金额/贷方调整金额
- interface扩展
- 编制提示加源模板A27原文

## 文件6: n2/inspection/N2TabPolicyCheck.vue — 表头分组+过程

- 前5列包裹"税费项目及适用税率"父column
- 新增"二、审计过程" textarea card + persist N2-4-process

## 文件7: n2/inspection/N2TabRecognition.vue — 新增行+过程+统计

- "+ 新增税种行"按钮(同时push endRows+beginRows)
- "二、审计过程" textarea + persist N2-5-process
- diffStats computed(filled/total/withDiff) + el-tag

## 文件8: n2/inspection/N2TabTaxCheck.vue — 完全重写凭证级

- useK1VoucherCheck(itemId:'N2-11-voucher-check', allResponses从useN2FormData)
- 审计目标3项
- 测试原因checkbox(5项) persist N2-11-test-meta
- 凭证表全列(日期/编号/业务/对方科目/明细科目/借贷方/支持性文件/核对1-5/索引/异常/备注)
- 检查比例(仅借方/贷方,滤掉期末余额行)
- 真抽凭GtVoucherSamplingEngine account-code=2221
- AI真回填+结论模板A/B/C
- 列设置⚙popover(12列checkbox, localStorage n2-11-column-prefs, 3列默认隐藏)

## 文件9: n2/calc/N2TabVatCalc.vue — 补(二)(三)+交叉验证

- 审计目标alert
- (二)销项测算: 按品种动态行+合计+待转调节+差异验证vs(一)销项
- (三)进项测算: 按类别动态行+合计+3调节项+差异验证vs(一)进项
- 按月表后cross-check-bar(月合计vs品种合计tag)
- handleCellChange加 void vatCalc.syncVatPayable() (P3-2联动)
- persist: N2-6-output-calc + N2-6-input-calc
- AI真回填(context转str)

## 文件10: n2/calc/N2TabExportRefund.vue — 22栏公式引擎

- 22行REFUND_TEMPLATE带_auto标记(12行公式行)
- 参数区: taxRateParam/refundRateParam/exemptMaterialCost
- recalcLedger()全公式(栏2=3+4, 6=4+5, 8=6×(征-退), 10=原材料×(征-退), 11/12互斥, 13=6×退, 15=原材料×退, 16/17互斥, 20=18-19, 21=min(16,20), 22=16-21)
- 公式行不可编辑(绿底虚线)
- 核心结论(栏21/22/11)
- 验证申报表一致性按钮(P4-1)
- 持久化: {params, rows}格式向后兼容
- 编制提示15条全文

## 文件11: n2/calc/N2TabOtherTaxCalc.vue — 补行+差额

- allCalcRows computed(合并auto+manual行)
- 新增4手动行: 消费税/资源税/土地使用税/车船税
- 新增列: 应税项目/计税依据/账面计提/差额(auto红字)
- persist: N2-8-manual-rows

## 文件12: n2/calc/N2TabPropertyTax.vue — 补2列

- "不计税原值"列(从价时可填)
- "当年月份"列(1-12 number)
- tooltip公式更新

## 文件13: n2/calc/N2TabLvt.vue — 扣除明细+面积

- "扣除明细"列(button→弹窗)
- el-dialog 5子项(取得土地/开发成本/费用/税金/加计)+合计auto+确认回填
- 面积参考表card(数量/收入/单价/成本×可销售/已售/未售auto/索引)
- persist: N2-10-area

## 文件14: n2/core/N2TabDisclosureListed.vue — 完全重写2列+增强

- 列: 税项/期末余额/上年年末余额(删掉旧4列)
- 变动率辅助列(>30%黄>50%红)
- N2-1勾稽(n21AuditedTotal computed, tag✓/⚠)
- 说明区: 固定提示琥珀块(3段不可编辑) + textarea补充
- seedFromAdjudication

## 文件15: n2/core/N2TabDisclosureSoe.vue — 删编造+增强

- 删"应缴国有资本收益"
- 列保持: 项目/期初/本期应交/本期已交/期末auto
- N2-1勾稽(同上市版)
- 说明区: 固定提示琥珀块 + textarea
- seedFromAdjudication

## 文件16: n2/core/N2TabIndex.vue — 进度动态化

- SHEET_PROGRESS_KEYS映射(code→item_id数组)
- progressByCode()从allResponses检测
- sheetRows全部改用progressByCode

## 文件17(后端): _n2_taxes_payable.py

- _fetch_tb_data修列名: begin_balance→opening_balance, end_balance→closing_balance, standard_account_code→account_code
- 新增_build_adjudication_prefill: 查2221%叶子→_classify_tax_type按名称归类→abs()负债→JSON
- render()末尾注入prefill(仅无持久化时)

## 跳过项

- P3-5 provide/inject收敛: 回归风险高,功能无损仅冗余请求
- P4-2 导入导出: 除N2-2外数据量小(<20行)

## 执行方式

新会话按文件编号1-17逐个fs_write/str_replace，每3-5个文件做一次Vite transform验证(curl localhost:3030)。全部完成后git add+commit+push。
