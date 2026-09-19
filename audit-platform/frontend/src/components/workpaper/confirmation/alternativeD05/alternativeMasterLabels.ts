/**
 * alternativeMasterLabels.ts — 替代程序**主表**（master 列表）按循环的文案配置
 *
 * spec: g0-confirmation-source-alignment，Task 14 补强（Requirement 7.1 / 7.6 / 11.1）
 *
 * ─── 为什么需要它（2026-08-04 用户看界面截图后指出）─────────────────────────
 * `AlternativeD05Master.vue` 是**七枢纽共享**主表（D0-5 / D0-6 / F0-5 / F0-6 / H0-5 /
 * K0-6 / G0-6 都在用），但其文案是 D0-5 **销售循环**写死的：
 *   `供应商/客户名称` · `新增公司` · `从 D0-1 带入` · `收款比例` · `出库比例` · 占位符 `D0-`
 * 挂在 G0-6（投资循环替代程序）上就成了「投资循环里问供应商、看出库比例」。
 *
 * 🔴 源模板 `替代程序检查表G0-6` **本身没有主表** —— 它是单主体一张表（表头只有
 * `A5 会计科目：` / `D5 投资产品/名称：`）。主从列表是平台级增强（便于一张底稿管多个
 * 被投资单位），增强本身合理，但**文案必须按循环**，否则术语与源模板脱节。
 *
 * ─── 零回归设计 ──────────────────────────────────────────────────────────────
 * 本模块只提供**可选**配置：`AlternativeD05Master` 的 `labels` prop 不传时套用
 * `DEFAULT_ALTERNATIVE_MASTER_LABELS`，其字面与改造前**逐字节相同** → 未传配置的
 * 六个枢纽渲染结果不变（守卫按基线常量断言）。
 *
 * 🟡 平台级遗留（本 spec 只登记不做）：F0-5 / F0-6 / H0-5 / K0-6 / D0-6 的主表同样
 * 显示「供应商/客户名称 / 收款比例 / 出库比例 / 从 D0-1 带入」，与各自循环语义不符
 * （预付账款 / 固定资产 / 递延收益…）。它们各自的 spec 接本模块即可修，改动量 = 一个
 * `labels` 常量 + 一处 prop 传参。
 */

/** 主表比例列（`type` 保持 `'receipt' | 'shipment'` → master 的 prop 签名不变） */
export interface AlternativeMasterRatioColumn {
  type: 'receipt' | 'shipment'
  label: string
}

export interface AlternativeMasterLabels {
  /** 「新增」按钮 */
  addButton: string
  /** 「从 X0-1 带入」按钮（X0-1 = 该循环的函证结果汇总表） */
  importFromSummary: string
  /** 主体名称列表头 */
  entityColumn: string
  /** 主体名称输入框占位符 */
  entityPlaceholder: string
  /** 函证索引号输入框占位符 */
  confirmIndexPlaceholder: string
  /** 两个检查比例列 */
  ratioColumns: readonly AlternativeMasterRatioColumn[]
  /** 空态文案 */
  emptyText: string
}

/**
 * 默认文案 = **改造前 `AlternativeD05Master.vue` 的字面，逐字节不变**。
 *
 * 🔴 改这里等于同时改 6 个未传 `labels` 的枢纽 → 守卫 `alternativeMasterLabels.spec.ts`
 * 以基线常量钉死，任何改动都会打红并要求说明。
 */
export const DEFAULT_ALTERNATIVE_MASTER_LABELS: AlternativeMasterLabels = Object.freeze({
  addButton: '新增公司',
  importFromSummary: '从 D0-1 带入',
  entityColumn: '供应商/客户名称',
  entityPlaceholder: '单位名称',
  confirmIndexPlaceholder: 'D0-',
  ratioColumns: Object.freeze([
    { type: 'receipt', label: '收款比例' },
    { type: 'shipment', label: '出库比例' },
  ] as const),
  emptyText: '暂无公司记录，请新增或从 D0-1 带入未回函公司',
})

/** 合并调用方配置与默认值（未声明的项回落默认 → 部分覆盖安全） */
export function resolveAlternativeMasterLabels(
  overrides?: Partial<AlternativeMasterLabels> | null,
): AlternativeMasterLabels {
  if (!overrides) return DEFAULT_ALTERNATIVE_MASTER_LABELS
  return {
    ...DEFAULT_ALTERNATIVE_MASTER_LABELS,
    ...overrides,
    ratioColumns: overrides.ratioColumns ?? DEFAULT_ALTERNATIVE_MASTER_LABELS.ratioColumns,
  }
}
