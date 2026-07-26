/**
 * H4-2 明细表四表取数种子 — 纯函数
 *
 * 从后端 render 输出的 `detail_prefill` 映射到 H4DetailRow schema，
 * 遵循 Persist-First：已有 H4-2-rows 时返回 null 不种子。
 *
 * @module h4DetailPrefill
 * Requirements: 1 (H4-2 从 tb_balance 叶子自动种子)
 */

export interface H4PrefillItem {
  category: string
  name: string
  accountCode: string
  beginAmount: number
  purchaseAmount: number
  usageAmount: number
  endAmount: number
  source: string
}

/**
 * Persist-First 种子构建。
 *
 * @param prefill - 后端 html_data.detail_prefill（可能为 null/undefined/空）
 * @param existingRowsJson - allResponses 中 H4-2-rows 的 remark（JSON 字符串或 null）
 * @returns 映射后的种子行数组，或 null（表示不种子）
 */
export function buildH4DetailSeedRows(
  prefill: H4PrefillItem[] | null | undefined,
  existingRowsJson: string | null | undefined,
): Record<string, any>[] | null {
  // Persist-First：已有数据不覆盖
  if (existingRowsJson) {
    try {
      const existing = JSON.parse(existingRowsJson)
      if (Array.isArray(existing) && existing.length > 0) {
        return null
      }
    } catch {
      // 解析失败视为无数据
    }
  }

  if (!prefill || !Array.isArray(prefill) || prefill.length === 0) {
    return null
  }

  return prefill.map((item, idx) => ({
    rowId: `seed-${idx}`,
    category: item.category || '其他',
    name: item.name || '',
    spec: '',
    unit: '',
    supplier: '',
    beginQty: 0,
    increaseQty: 0,
    decreaseQty: 0,
    beginAmount: item.beginAmount || 0,
    purchaseAmount: item.purchaseAmount || 0,
    otherIncrease: 0,
    usageAmount: item.usageAmount || 0,
    returnAmount: 0,
    scrapAmount: 0,
    otherDecrease: 0,
    ajeBegin: 0,
    ajeIncrease: 0,
    ajeDecrease: 0,
    impairBegin: 0,
    impairIncrease: 0,
    impairDecrease: 0,
    ajeImpair: 0,
    aging: '',
    quality: '',
    // 计算列由 composable 派生
    endAmount: item.endAmount || 0,
    // 溯源标记
    source: item.source || 'tb_balance',
    accountCode: item.accountCode || '',
  }))
}

/**
 * H4-5↔H2 勾稽纯函数
 */
export interface H4H2Reconcile {
  h4UsageTotal: number
  h2MaterialTotal: number
  diff: number
  isMatch: boolean
}

export function buildH4H2Reconcile(h4UsageTotal: number, h2MaterialTotal: number): H4H2Reconcile {
  const diff = h4UsageTotal - h2MaterialTotal
  return {
    h4UsageTotal,
    h2MaterialTotal,
    diff,
    isMatch: Math.abs(diff) < 1,
  }
}
