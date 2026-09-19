/**
 * f0MasterLabels.ts — F0-5 / F0-6 替代程序主表文案（按源模板对齐）
 *
 * spec: f0-confirmation-linkage-and-structural-enhancement，复盘 P2
 *
 * ─── 为什么需要它 ────────────────────────────────────────────────────────────
 * `AlternativeD05Master.vue` 是**七枢纽共享**主表，其默认文案是 D0-5 **销售循环**
 * 写死的（`供应商/客户名称` · `从 D0-1 带入` · `收款比例` · `出库比例` · 占位符
 * `D0-`）。2026-08-04 浏览器实测在 F0-5 页面上直接看到按钮写「从 D0-1 带入」，
 * 而 handler 传的是 `'F0-1'` —— **标签与行为不一致**，审计师会以为点错了表。
 *
 * 共享机制 `alternativeMasterLabels.ts`（G0 spec Task 14 建）已把 F0-5 / F0-6
 * 显式登记为待接入方，原文：「它们各自的 spec 接本模块即可修，改动量 = 一个
 * `labels` 常量 + 一处 prop 传参」。本模块即该接入。
 *
 * ─── 每一项的源模板依据（openpyxl 直读 `F/F0 存货循环函证.xlsx`，禁自造）─────
 * | 项 | 依据 | 源单元格 |
 * |----|------|---------|
 * | `供应商名称` | 两表表头逐字 `供应商名称：` | `F0-5!A5` / `F0-6!A5` |
 * | `从 F0-1 带入` | F0-1 是本循环的函证结果汇总表 | 底稿目录 |
 * | `F0-` | 询证函索引号前缀（F0-1!B 列形态） | `F0-1!B` |
 * | `本期付款检查比例` | 逐字 | `F0-5!K11` |
 * | `本期入库检查比例` | 逐字 | `F0-6!K11` |
 *
 * ─── 为什么 F0-5 与 F0-6 共用一份（不各写一份）────────────────────────────────
 * 源模板每张表只有**一个**比例列（F0-5 = 付款 / F0-6 = 入库），而共享 master 有
 * **两个**比例列（平台增强）。两表的 `metricRatioKeys` 均为
 * `{receipt:'payment', shipment:'inbound'}`（见各自 `useAlternativeF0{5,6}Data`）
 * → 两表的 `type → 业务含义` **完全相同**，故文案只需一份，两列名分别取自两张源
 * 模板的 K11。写成两个内容相同的常量只会制造「改一处漏一处」的漂移面。
 *
 * 🔴 `ratioColumns[].type` 必须保持 `'receipt' | 'shipment'` —— 那是 master 的
 * prop 签名。F0-5 与 F0-6 的 **block 映射相反**（F0-5 payment=block3 /
 * F0-6 payment=block4），但那是 ratio 规则层的事，与本文案层无关。
 */
import type { AlternativeMasterLabels } from '../alternativeD05/alternativeMasterLabels'

/**
 * F0-5 / F0-6 共用的替代程序主表文案（存货循环：预付账款 / 应付票据 / 应付账款）。
 *
 * 两个比例列的 label 分别逐字取自 `F0-5!K11`（付款）与 `F0-6!K11`（入库），
 * 顺序对齐 master 的 `receipt`（=payment）/ `shipment`（=inbound）语义。
 */
export const F0_ALTERNATIVE_MASTER_LABELS: AlternativeMasterLabels = Object.freeze({
  addButton: '新增供应商',
  importFromSummary: '从 F0-1 带入',
  entityColumn: '供应商名称',
  entityPlaceholder: '供应商名称',
  confirmIndexPlaceholder: 'F0-',
  ratioColumns: Object.freeze([
    { type: 'receipt', label: '本期付款检查比例' },
    { type: 'shipment', label: '本期入库检查比例' },
  ] as const),
  emptyText: '暂无供应商记录，请新增或从 F0-1 带入未回函供应商',
})
